import Cocoa

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let engine = EngineProcess()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)  // kein Dock-Icon (Menüleisten-App)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.title = "🎙️"

        render(status: "Startet Engine…")
        engine.start { [weak self] state in
            self?.handleEngineState(state)
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        engine.stop()
    }

    private func handleEngineState(_ state: EngineProcess.State) {
        switch state {
        case .stopped:
            render(status: "Gestoppt")
        case .starting:
            render(status: "Startet Engine…")
        case .running:
            render(status: "Bereit")
        case .crashed:
            render(status: "Fehler — siehe Konsole.app (Prozess „LocalFlow“)")
        }
    }

    private func render(status: String) {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "LocalFlow — \(status)", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Beenden", action: #selector(quit), keyEquivalent: "q", target: self)
        statusItem.menu = menu
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}

private extension NSMenu {
    @discardableResult
    func addItem(withTitle title: String, action: Selector, keyEquivalent: String,
                 target: AnyObject) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
        item.target = target
        addItem(item)
        return item
    }
}
