import { app, BrowserWindow, Menu, Tray, nativeImage } from 'electron';

export function createTray(win: BrowserWindow) {
  const tray = new Tray(nativeImage.createEmpty());
  tray.setToolTip('AURA');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show AURA', click: () => { win.show(); win.focus(); } },
    { label: 'Hide AURA', click: () => win.hide() },
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
