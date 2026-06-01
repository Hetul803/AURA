import { app, BrowserWindow, Menu, Tray, nativeImage } from 'electron';

export function createTray(win: BrowserWindow) {
  const tray = new Tray(nativeImage.createEmpty());
  tray.setToolTip('Aegisure');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show Aegisure', click: () => { win.show(); win.focus(); } },
    { label: 'Hide Aegisure', click: () => win.hide() },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ]));
  tray.on('click', () => {
    if (win.isVisible()) win.hide();
    else {
      win.show();
      win.focus();
    }
  });
  return tray;
}
