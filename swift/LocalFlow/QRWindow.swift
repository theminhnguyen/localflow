import Cocoa

/// Kleines eigenständiges Fenster, das den Kopplungs-QR-Code anzeigt (Gegenstück
/// zu menubar._render_qr(), das die PNG stattdessen als Datei in Preview.app
/// öffnet). Wird von AppDelegate mit einer starken Referenz am Leben gehalten,
/// solange der Nutzer es offen lässt.
final class QRWindowController: NSWindowController {
    convenience init(image: NSImage, title: String) {
        let size: CGFloat = 280
        let margin: CGFloat = 20

        let imageView = NSImageView(frame: NSRect(x: margin, y: margin,
                                                    width: size, height: size))
        imageView.image = image
        imageView.imageScaling = .scaleProportionallyUpOrDown

        let contentView = NSView(frame: NSRect(x: 0, y: 0,
                                                width: size + margin * 2,
                                                height: size + margin * 2))
        contentView.addSubview(imageView)

        let window = NSWindow(contentRect: contentView.frame,
                               styleMask: [.titled, .closable],
                               backing: .buffered, defer: false)
        window.title = title
        window.contentView = contentView
        window.isReleasedWhenClosed = false
        window.center()

        self.init(window: window)
    }
}
