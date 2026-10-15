import AppKit
import Foundation

/// AppKit Services entry points. NSServices passes filenames on the pasteboard;
/// file URLs are preferred so spaces and non-ASCII names remain intact.
final class BytepleatServiceProvider: NSObject {
    @objc func compressWithBytepleat(_ pasteboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        if let failure = launch(action: "create", pasteboard: pasteboard) { error.pointee = failure as NSString }
    }

    @objc func extractWithBytepleat(_ pasteboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        if let failure = launch(action: "extract", pasteboard: pasteboard) { error.pointee = failure as NSString }
    }

    private func launch(action: String, pasteboard: NSPasteboard) -> String? {
        guard let paths = Self.selectedPaths(from: pasteboard), !paths.isEmpty else {
            return "Select local files or folders to use Bytepleat."
        }
        guard let appURL = Self.applicationURL() else {
            return "Cannot locate Bytepleat.app. Reinstall the Bytepleat Services integration."
        }
        // A direct argv launch reaches Tauri's single-instance broker even when
        // the app is already running; LaunchServices may ignore new arguments.
        let process = Process()
        process.executableURL = appURL.appendingPathComponent("Contents/MacOS/bytepleat-desktop")
        process.arguments = ["--\(action)", "--"] + paths
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do { try process.run() }
        catch { return "Could not open Bytepleat: \(error.localizedDescription)" }
        return nil
    }

    private static func selectedPaths(from pasteboard: NSPasteboard) -> [String]? {
        if let urls = pasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL], !urls.isEmpty {
            return urls.map(\.path)
        }
        if let files = pasteboard.propertyList(forType: NSPasteboard.PasteboardType("NSFilenamesPboardType")) as? [String], !files.isEmpty {
            return files
        }
        return nil
    }

    private static func applicationURL() -> URL? {
        if let explicit = ProcessInfo.processInfo.environment["BYTEPLEAT_APP_PATH"],
           let url = validApplication(at: URL(fileURLWithPath: explicit, isDirectory: true)) { return url }

        // Installer writes this optional explicit app path into this service bundle.
        if let configured = Bundle.main.object(forInfoDictionaryKey: "BytepleatApplicationPath") as? String,
           let url = validApplication(at: URL(fileURLWithPath: configured, isDirectory: true)) { return url }

        // Also support app bundles located next to the installed service bundle.
        var directory = Bundle.main.bundleURL.deletingLastPathComponent()
        for _ in 0..<5 {
            let candidate = directory.appendingPathComponent("Bytepleat.app", isDirectory: true)
            if let url = validApplication(at: candidate) { return url }
            let parent = directory.deletingLastPathComponent()
            if parent == directory { break }
            directory = parent
        }
        return nil
    }

    private static func validApplication(at url: URL) -> URL? {
        guard FileManager.default.fileExists(atPath: url.appendingPathComponent("Contents/Info.plist").path),
              FileManager.default.fileExists(atPath: url.appendingPathComponent("Contents/MacOS/bytepleat-desktop").path) else { return nil }
        return url
    }
}

let application = NSApplication.shared
let provider = BytepleatServiceProvider()
application.servicesProvider = provider
NSUpdateDynamicServices()
application.run()
