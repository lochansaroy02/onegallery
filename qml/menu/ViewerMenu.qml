import QtQuick
import QtQuick.Controls
import ".."

// The viewer's ⋮ menu: themed like the rest of the app, with icons, grouped actions,
// Set as ▸ (wallpaper / lock screen / both) and Print… for pictures.
StyledMenu {
    id: menu
    property var viewer: null
    readonly property var win: viewer ? viewer.win : null
    readonly property var info: viewer ? viewer.info : ({})
    readonly property bool isPicture: info.video !== true
    readonly property bool usable: info.available === true
    readonly property bool isPrivate: info.private === true
    readonly property int setAsIndex: 5   // after Open Gallery, Play video, Capture frame, Details, divider

    // "Set as" only exists for pictures: added / removed each time the menu opens
    property StyledMenu setAsMenu: StyledMenu {
        title: qsTr("Set as")
        iconName: "wallpaper"
        enabled: menu.usable && gallery.wallpaperSupported
        AppMenuItem {
            text: qsTr("Wallpaper")
            iconName: "monitor"
            shortcutText: "Ctrl+Shift+B"
            onTriggered: gallery.setAsWallpaper(menu.info.path, "wallpaper")
        }
        AppMenuItem {
            text: qsTr("Lock screen")
            visible: gallery.lockScreenSupported
            iconName: "lock"
            shortcutText: "Ctrl+Shift+L"
            onTriggered: gallery.setAsWallpaper(menu.info.path, "lockscreen")
        }
        AppMenuItem {
            text: qsTr("Wallpaper and lock screen")
            visible: gallery.lockScreenSupported
            iconName: "layers"
            onTriggered: gallery.setAsWallpaper(menu.info.path, "both")
        }
    }
    property bool setAsShown: false
    onAboutToShow: {
        const want = isPicture && !isPrivate
        if (want && !setAsShown) { insertMenu(setAsIndex, setAsMenu); setAsShown = true }
        else if (!want && setAsShown) { removeMenu(setAsMenu); setAsShown = false }
    }

    AppMenuItem {
        text: qsTr("Open One Gallery")
        iconName: "pictures"
        visible: menu.win !== null && menu.win.standalone
        onTriggered: menu.win.showLibrary()
    }
    AppMenuItem {
        text: qsTr("Play video")
        iconName: "play"
        shortcutText: "Enter"
        visible: !menu.isPicture
        onTriggered: menu.viewer.playCurrent()
    }
    AppMenuItem {
        text: qsTr("Capture frame")
        iconName: "camera"
        shortcutText: "S"
        visible: !menu.isPicture && !menu.isPrivate
        enabled: menu.usable && gallery.videoThumbnailsSupported
        onTriggered: menu.viewer.captureFrame()
    }
    AppMenuItem {
        text: qsTr("Details")
        iconName: "info"
        shortcutText: "I"
        onTriggered: menu.viewer.detailsOpen = true
    }
    MenuDivider { }
    AppMenuItem {
        text: qsTr("Print…")
        iconName: "print"
        shortcutText: "Ctrl+P"
        visible: menu.isPicture && !menu.isPrivate
        enabled: menu.usable && gallery.printingSupported
        onTriggered: menu.win.printPicture(menu.info)
    }
    MenuDivider { visible: menu.isPicture && !menu.isPrivate }
    // private album: the only ways out
    AppMenuItem {
        text: qsTr("Move out of private album")
        iconName: "unlock"
        visible: menu.isPrivate
        onTriggered: menu.viewer.moveCurrentOutOfPrivate()
    }
    AppMenuItem {
        text: qsTr("Delete permanently")
        iconName: "trash"
        danger: true
        visible: menu.isPrivate
        onTriggered: menu.viewer.deleteCurrent()
    }
    AppMenuItem {
        text: qsTr("Open with…")
        visible: !menu.isPrivate
        iconName: "openWith"
        onTriggered: menu.win.openWith([menu.info.path])
    }
    AppMenuItem {
        text: qsTr("Open in default app")
        iconName: "monitor"
        visible: !menu.isPrivate
        onTriggered: gallery.openExternally(menu.info.path)
    }
    AppMenuItem {
        text: qsTr("Show in folder")
        iconName: "showFolder"
        visible: !menu.isPrivate
        onTriggered: gallery.showInFolder(menu.info.path)
    }
    MenuDivider { visible: !menu.isPrivate }
    AppMenuItem {
        text: qsTr("Move to private album")
        iconName: "lock"
        shortcutText: "Ctrl+Shift+H"
        visible: !menu.isPrivate
        enabled: menu.usable && privateAlbum.supported
        onTriggered: menu.viewer.moveCurrentToPrivate()
    }
    AppMenuItem {
        text: menu.isPicture ? qsTr("Copy picture") : qsTr("Copy video")
        visible: !menu.isPrivate
        iconName: "copy"
        shortcutText: "Ctrl+C"
        onTriggered: gallery.shareFiles([menu.info.path])
    }
    AppMenuItem {
        text: qsTr("Copy path")
        iconName: "file"
        visible: !menu.isPrivate
        shortcutText: "Ctrl+Shift+C"
        onTriggered: gallery.copyPaths([menu.info.path])
    }
    MenuDivider { visible: menu.viewer !== null && menu.viewer.canRevert }
    AppMenuItem {
        text: qsTr("Revert to original")
        iconName: "undo"
        danger: true
        visible: menu.viewer !== null && menu.viewer.canRevert
        onTriggered: menu.win.confirm(
            qsTr("Revert to original?"),
            qsTr("All edits you saved to this picture are removed and the original file is restored."),
            qsTr("Revert"), function() { editor.revertOriginal(menu.info.path) })
    }
}
