from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DeviceAdapterSpec:
    adapter_id: str
    name: str
    surface: str
    status: str
    description: str
    context_sources: list[str] = field(default_factory=list)
    input_methods: list[str] = field(default_factory=list)
    output_methods: list[str] = field(default_factory=list)
    action_groups: list[str] = field(default_factory=list)
    policy_constraints: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ADAPTERS: dict[str, DeviceAdapterSpec] = {
    'desktop-local': DeviceAdapterSpec(
        adapter_id='desktop-local',
        name='Local Desktop',
        surface='desktop',
        status='available',
        description='Primary AURA surface for local OS context, shell, filesystem, clipboard, and overlay approvals.',
        context_sources=['active_app', 'active_window', 'clipboard', 'selected_text', 'current_folder', 'current_repo'],
        input_methods=['text_command', 'global_hotkey', 'overlay', 'voice_later'],
        output_methods=['overlay', 'desktop_notification_later', 'paste_back', 'run_timeline'],
        action_groups=['os', 'filesystem', 'code', 'assist', 'control'],
        policy_constraints=['confirm_destructive_actions', 'confirm_external_sends', 'redact_secrets'],
    ),
    'browser-visible': DeviceAdapterSpec(
        adapter_id='browser-visible',
        name='Visible Browser',
        surface='browser',
        status='available',
        description='Browser automation adapter for navigation, reading, clicking, typing, and upload workflows.',
        context_sources=['active_browser_url', 'browser_title', 'page_text_later'],
        input_methods=['browser_context', 'overlay_command'],
        output_methods=['browser_action', 'run_timeline'],
        action_groups=['browser'],
        policy_constraints=['confirm_form_submission', 'confirm_purchase', 'confirm_sensitive_site_actions'],
    ),
    'phone-companion': DeviceAdapterSpec(
        adapter_id='phone-companion',
        name='Phone Companion',
        surface='phone',
        status='planned',
        description='Future mobile voice, notifications, approvals, memory access, and phone-to-desktop handoff.',
        context_sources=['mobile_app_context_later', 'notification_context_later', 'share_sheet_later', 'location_later'],
        input_methods=['voice_later', 'mobile_text_later', 'quick_approval_later'],
        output_methods=['notification_later', 'mobile_app_later', 'handoff_later'],
        action_groups=['phone_future', 'approval'],
        policy_constraints=['explicit_sync_consent', 'limited_background_capture', 'device_lock_respect'],
    ),
    'home-assistant': DeviceAdapterSpec(
        adapter_id='home-assistant',
        name='AURA Home',
        surface='home',
        status='planned',
        description='Future household routines, smart home control, and family-aware boundaries.',
        context_sources=['home_device_state_later', 'household_calendar_later'],
        input_methods=['voice_later', 'ambient_later'],
        output_methods=['speaker_later', 'home_notification_later'],
        action_groups=['home_future'],
        policy_constraints=['household_boundary_policy', 'confirm_security_sensitive_home_actions'],
    ),
    'car-assistant': DeviceAdapterSpec(
        adapter_id='car-assistant',
        name='AURA Car',
        surface='car',
        status='planned',
        description='Future safety-first driving assistant for voice, navigation, messages with approval, and handoff.',
        context_sources=['navigation_later', 'calendar_later', 'vehicle_state_later'],
        input_methods=['voice_later', 'steering_controls_later'],
        output_methods=['voice_later', 'car_display_later', 'handoff_later'],
        action_groups=['car_future'],
        policy_constraints=['driving_safe_actions_only', 'no_visual_complexity_while_driving'],
    ),
    'enterprise-workspace': DeviceAdapterSpec(
        adapter_id='enterprise-workspace',
        name='Enterprise Workspace',
        surface='enterprise',
        status='planned',
        description='Future company AURA adapter for RBAC, admin policy, company memory, and team workflow agents.',
        context_sources=['company_apps_later', 'team_memory_later', 'identity_provider_later'],
        input_methods=['company_command_later', 'workflow_trigger_later'],
        output_methods=['team_timeline_later', 'admin_audit_later', 'company_app_later'],
        action_groups=['enterprise_future', 'approval', 'audit'],
        policy_constraints=['rbac_required', 'tenant_isolation', 'company_audit_required', 'personal_company_boundary'],
    ),
}


def list_device_adapters() -> list[dict[str, Any]]:
    return [adapter.to_dict() for adapter in _ADAPTERS.values()]


def get_device_adapter(adapter_id: str) -> dict[str, Any] | None:
    adapter = _ADAPTERS.get(adapter_id)
    return adapter.to_dict() if adapter else None
