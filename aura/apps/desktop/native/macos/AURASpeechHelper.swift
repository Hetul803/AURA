import AVFoundation
import Foundation
import Speech

struct JsonLine {
    static func print(_ payload: [String: Any]) {
        let data = try! JSONSerialization.data(withJSONObject: payload, options: [])
        Swift.print(String(data: data, encoding: .utf8)!)
        fflush(stdout)
    }
}

func argValue(_ name: String, fallback: String) -> String {
    let args = CommandLine.arguments
    if let index = args.firstIndex(of: name), index + 1 < args.count {
        return args[index + 1]
    }
    return fallback
}

func requestSpeechAuthorization() -> Bool {
    let semaphore = DispatchSemaphore(value: 0)
    var allowed = false
    SFSpeechRecognizer.requestAuthorization { status in
        allowed = status == .authorized
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 12)
    return allowed
}

func requestMicrophoneAuthorization() -> Bool {
    let semaphore = DispatchSemaphore(value: 0)
    var allowed = false
    AVCaptureDevice.requestAccess(for: .audio) { granted in
        allowed = granted
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 12)
    return allowed
}

let locale = Locale(identifier: argValue("--locale", fallback: "en-US"))
let duration = Double(argValue("--duration", fallback: "8")) ?? 8.0

guard requestSpeechAuthorization() else {
    JsonLine.print(["ok": false, "status": "speech_permission_denied", "message": "Enable Speech Recognition permission for AURA in macOS System Settings."])
    exit(2)
}

guard requestMicrophoneAuthorization() else {
    JsonLine.print(["ok": false, "status": "microphone_permission_denied", "message": "Enable Microphone permission for AURA in macOS System Settings."])
    exit(3)
}

guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
    JsonLine.print(["ok": false, "status": "speech_recognizer_unavailable", "message": "Apple Speech recognizer is unavailable for this locale right now."])
    exit(4)
}

let audioEngine = AVAudioEngine()
let request = SFSpeechAudioBufferRecognitionRequest()
request.shouldReportPartialResults = true
if #available(macOS 13.0, *) {
    request.requiresOnDeviceRecognition = false
}

var bestTranscript = ""
var finalTranscript = ""
var recognitionError: String?
let done = DispatchSemaphore(value: 0)

let task = recognizer.recognitionTask(with: request) { result, error in
    if let result = result {
        bestTranscript = result.bestTranscription.formattedString
        if result.isFinal {
            finalTranscript = bestTranscript
            done.signal()
        }
    }
    if let error = error {
        recognitionError = error.localizedDescription
        done.signal()
    }
}

let input = audioEngine.inputNode
let format = input.outputFormat(forBus: 0)
input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
    request.append(buffer)
}

do {
    audioEngine.prepare()
    try audioEngine.start()
} catch {
    JsonLine.print(["ok": false, "status": "audio_engine_failed", "message": error.localizedDescription])
    exit(5)
}

DispatchQueue.global().asyncAfter(deadline: .now() + duration) {
    request.endAudio()
    done.signal()
}

JsonLine.print(["ok": true, "status": "listening", "provider": "apple_speech", "duration_seconds": duration])
_ = done.wait(timeout: .now() + duration + 4)

audioEngine.stop()
input.removeTap(onBus: 0)
request.endAudio()
task.cancel()

let transcript = finalTranscript.isEmpty ? bestTranscript : finalTranscript
if transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
    JsonLine.print(["ok": false, "status": recognitionError == nil ? "no_speech_detected" : "recognition_failed", "message": recognitionError ?? "I did not hear a command. Try again or type the command.", "provider": "apple_speech"])
} else {
    JsonLine.print(["ok": true, "status": "transcribed", "provider": "apple_speech", "transcript": transcript])
}

