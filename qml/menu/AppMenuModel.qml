import QtQuick
import QtQuick.Controls
import QtQuick.Window
import ".."

// The application menu, declared once: File, Edit, View, Go, Settings, Help.
// Items enable themselves from context (a picture open, a selection, the editor...).
QtObject {
    id: app
    property var win: null
    property var viewer: null
    property var editorPage: null

    // ---- context ------------------------------------------------------------------------------
    readonly property bool viewing: viewer !== null && viewer.visible && !viewer.closing
    readonly property bool editing: editorPage !== null && editorPage.visible
    readonly property var grid: win ? win.currentGrid : null
    readonly property bool selecting: !viewing && !editing && grid !== null && grid.selectMode
                                      && grid.photoModel.selectionCount > 0
    // inside the private album: no sharing, opening elsewhere, copying, editing...
    readonly property bool inPrivate: (viewing && viewer.info.private === true)
                                      || (!viewing && grid !== null && grid.photoModel === privatePhotos)
    readonly property bool hasContext: !inPrivate && (editing || (viewing && !!viewer.info.path) || selecting)
    readonly property bool privateContext: inPrivate && ((viewing && !!viewer.info.path)
                                                         || (selecting && grid.photoModel === privatePhotos))
    readonly property bool viewingLibraryPicture: viewing && viewer.info.external !== true
    readonly property bool viewingPicture: viewing && viewer.info.video !== true && viewer.info.available === true
                                           && viewer.info.private !== true
    readonly property bool canRotate: hasContext && !editing && !(viewing && viewer.info.available === false)
                                      && !(viewing && viewer.info.video === true)

    function paths() {
        if (editing) return [editor.path]
        if (viewing) return viewer.info.path ? [viewer.info.path] : []
        if (selecting) return grid.photoModel.selectedPaths()
        return []
    }
    function finishSelection() {
        if (!viewing && grid && grid.selectMode) grid.exitSelection()
    }

    // ---- actions (also used by keyboard shortcuts) ------------------------------------------------
    function rotate(clockwise) {
        if (!canRotate) return
        editor.quickRotate(paths(), clockwise)
        finishSelection()
    }
    function toggleFavorite() {
        if (viewing) { viewer.toggleFavorite(); return }
        if (!selecting) return
        gallery.setFavorite(grid.photoModel.selectedIds(), !grid.photoModel.selectionAllFavorite())
        finishSelection()
    }
    function trash() {
        if (privateContext) {
            const ids = viewing ? [viewer.info.id] : grid.photoModel.selectedIds()
            win.deletePrivate(ids, viewing ? null : function() { finishSelection() })
            return
        }
        if (!hasContext || editing) return
        const done = viewing ? null : function() { finishSelection() }
        win.confirmDelete(paths(), done)
    }
    function jumpToYear(year) {
        win.goTab(0)
        Qt.callLater(function() {
            const g = win.currentGrid
            if (!g) return
            const index = g.photoModel.firstIndexOfYear(year)
            if (index >= 0) g.view.positionViewAtIndex(g.photoModel.rowForItem(index), ListView.Beginning)
        })
    }
    function goToToday() {
        win.goTab(0)
        Qt.callLater(function() {
            const g = win.currentGrid
            if (!g) return
            if (prefs.sortAscending) g.view.positionViewAtEnd()
            else g.view.positionViewAtBeginning()
        })
    }
    function baseName(path) { return path.replace(/^.*[\/\\]/, "") }

    // Real keyboard shortcuts for the items marked bindKey (the rest live in Main.qml).
    property Component shortcutComponent: Component {
        Shortcut { property var spec; context: Qt.ApplicationShortcut }
    }
    function installShortcuts(parentItem) {
        function walk(spec) {
            if (spec.bindKey && spec.shortcut !== "") {
                shortcutComponent.createObject(parentItem, {
                    spec: spec,
                    sequence: spec.shortcut,
                    enabled: Qt.binding(() => spec.enabled && spec.visible && !win.dialogOpen)
                }).activated.connect(function() { spec.triggered() })
            }
            for (const child of spec.items) walk(child)
        }
        for (const menu of menus) walk(menu)
    }

    // ---- the menus ------------------------------------------------------------------------------
    property list<QtObject> menus: [
        MenuSpec {
            text: qsTr("&File")
            MenuSpec { text: qsTr("Add Folder…"); shortcut: "Ctrl+O"; onTriggered: win.addFolder() }
            MenuSpec {
                text: qsTr("Exclude Sub-folders")
                submenu: true
                enabled: gallery.folders.length > 0 && !app.editing
                model: gallery.folders.map(f => ({ text: f.name + (f.excludes.length ? "  ·  " + f.excludes.length + " excluded" : ""), value: f }))
                onPicked: (value) => { if (app.viewing) app.viewer.close(); win.editExcludes(value.path, value.excludes) }
            }
            MenuSpec {
                text: qsTr("Open Picture…"); shortcut: "Ctrl+Shift+O"; bindKey: true
                enabled: !app.editing
                onTriggered: win.openPictureDialog()
            }
            MenuSpec {
                text: qsTr("Open Recent")
                submenu: true
                dynamicFirst: true
                enabled: prefs.recentFiles.length > 0
                model: prefs.recentFiles.map(p => ({ text: app.baseName(p), value: p }))
                onPicked: (value) => gallery.openFiles([value])
                MenuSpec { separator: true }
                MenuSpec { text: qsTr("Clear Recent"); onTriggered: prefs.clearRecent() }
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Save"); shortcut: "Ctrl+S"
                visible: app.editing
                enabled: app.editing && editor.dirty && !editor.saving
                onTriggered: app.editorPage.save()
            }
            MenuSpec {
                text: qsTr("Save as Copy"); shortcut: "Ctrl+Shift+S"
                visible: app.editing
                enabled: app.editing && editor.dirty && !editor.saving
                onTriggered: app.editorPage.saveCopy()
            }
            MenuSpec { separator: true; visible: app.editing }
            MenuSpec {
                text: qsTr("Share")
                submenu: true
                enabled: app.hasContext
                model: [{ text: qsTr("Copy to Clipboard"), value: "" }]
                       .concat(gallery.shareTargets.map(t => ({ text: t.name, value: t.id })))
                onPicked: (value) => { gallery.shareWith(value, app.paths()); app.finishSelection() }
            }
            MenuSpec { text: qsTr("Open With…"); enabled: app.hasContext; onTriggered: win.openWith(app.paths()) }
            MenuSpec {
                text: qsTr("Show in Folder"); enabled: app.hasContext
                onTriggered: gallery.showInFolder(app.paths()[0])
            }
            MenuSpec {
                text: qsTr("Set As")
                enabled: app.viewingPicture && gallery.wallpaperSupported
                MenuSpec {
                    text: qsTr("Wallpaper"); shortcut: "Ctrl+Shift+B"; bindKey: true
                    enabled: app.viewingPicture && gallery.wallpaperSupported
                    onTriggered: gallery.setAsWallpaper(app.viewer.info.path, "wallpaper")
                }
                MenuSpec {
                    text: qsTr("Lock Screen"); shortcut: "Ctrl+Shift+L"; bindKey: true
                    enabled: app.viewingPicture && gallery.wallpaperSupported
                    onTriggered: gallery.setAsWallpaper(app.viewer.info.path, "lockscreen")
                }
                MenuSpec { text: qsTr("Wallpaper and Lock Screen"); enabled: app.viewingPicture; onTriggered: gallery.setAsWallpaper(app.viewer.info.path, "both") }
            }
            MenuSpec {
                text: qsTr("Print…"); shortcut: "Ctrl+P"; bindKey: true
                enabled: app.viewingPicture && gallery.printingSupported
                onTriggered: win.printPicture(app.viewer.info)
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Rescan Folders"); shortcut: "F5"
                enabled: gallery.hasFolders && !gallery.scanning
                onTriggered: gallery.rescan()
            }
            MenuSpec {
                text: app.inPrivate ? qsTr("Delete Permanently") : qsTr("Move to Trash"); shortcut: "Del"
                enabled: (app.hasContext || app.privateContext) && !app.editing
                onTriggered: app.trash()
            }
            MenuSpec { separator: true }
            MenuSpec { text: qsTr("Quit"); shortcut: "Ctrl+Q"; bindKey: true; onTriggered: Qt.quit() }
        },

        MenuSpec {
            text: qsTr("&Edit")
            MenuSpec {
                text: qsTr("Undo"); shortcut: "Ctrl+Z"
                enabled: app.editing && editor.canUndo
                onTriggered: editor.undo()
            }
            MenuSpec {
                text: qsTr("Redo"); shortcut: "Ctrl+Shift+Z"
                enabled: app.editing && editor.canRedo
                onTriggered: editor.redo()
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Select All"); shortcut: "Ctrl+A"
                enabled: !app.viewing && !app.editing && app.grid !== null && app.grid.photoModel.itemCount > 0
                onTriggered: { app.grid.selectMode = true; app.grid.photoModel.selectAll() }
            }
            MenuSpec {
                text: qsTr("Deselect All"); shortcut: "Ctrl+Shift+A"; bindKey: true
                enabled: !app.viewing && app.grid !== null && app.grid.selectMode
                onTriggered: app.grid.exitSelection()
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Copy Picture"); shortcut: "Ctrl+C"; bindKey: true
                enabled: app.hasContext && !app.editing
                onTriggered: gallery.shareFiles(app.paths())
            }
            MenuSpec {
                text: qsTr("Copy Path"); shortcut: "Ctrl+Shift+C"; bindKey: true
                enabled: app.hasContext
                onTriggered: gallery.copyPaths(app.paths())
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Edit Picture…"); shortcut: "E"
                enabled: app.viewing && app.viewer.info.available === true && app.viewer.info.animated !== true
                         && app.viewer.info.video !== true && !app.inPrivate
                onTriggered: win.openEditor(app.viewer.info)
            }
            MenuSpec {
                text: qsTr("Rotate")
                enabled: app.canRotate
                MenuSpec { text: qsTr("Rotate Left"); shortcut: "Ctrl+L"; bindKey: true; enabled: app.canRotate; onTriggered: app.rotate(false) }
                MenuSpec { text: qsTr("Rotate Right"); shortcut: "Ctrl+R"; bindKey: true; enabled: app.canRotate; onTriggered: app.rotate(true) }
            }
            MenuSpec {
                text: app.viewing && app.viewer.info.favorite ? qsTr("Remove from Favorites") : qsTr("Add to Favorites")
                shortcut: "F"
                enabled: (app.viewingLibraryPicture || app.selecting) && !app.inPrivate
                onTriggered: app.toggleFavorite()
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Move to Private Album"); shortcut: "Ctrl+Shift+H"; bindKey: true
                enabled: app.hasContext && !app.editing && privateAlbum.supported
                onTriggered: win.moveToPrivate(app.paths(), function() { app.finishSelection() })
            }
            MenuSpec {
                text: qsTr("Move out of Private Album")
                visible: app.inPrivate
                enabled: app.privateContext
                onTriggered: win.moveOutOfPrivate(app.viewing ? [app.viewer.info.id] : app.grid.photoModel.selectedIds(),
                                                  app.viewing ? null : function() { app.finishSelection() })
            }
            MenuSpec {
                text: qsTr("Revert to Original")
                enabled: app.viewing && app.viewer.canRevert
                onTriggered: win.confirm(qsTr("Revert to original?"),
                                         qsTr("All edits you saved to this picture are removed and the original file is restored."),
                                         qsTr("Revert"), function() { editor.revertOriginal(app.viewer.info.path) })
            }
        },

        MenuSpec {
            text: qsTr("&View")
            MenuSpec {
                text: qsTr("Pictures"); shortcut: "Ctrl+1"; bindKey: true
                checkable: true; checked: win !== null && win.currentTab === 0
                onTriggered: win.goTab(0)
            }
            MenuSpec {
                text: qsTr("Videos"); shortcut: "Ctrl+2"; bindKey: true
                checkable: true; checked: win !== null && win.currentTab === 1
                onTriggered: win.goTab(1)
            }
            MenuSpec {
                text: qsTr("Albums"); shortcut: "Ctrl+3"; bindKey: true
                checkable: true; checked: win !== null && win.currentTab === 2
                onTriggered: win.goTab(2)
            }
            MenuSpec {
                text: qsTr("Collections"); shortcut: "Ctrl+4"; bindKey: true
                checkable: true; checked: win !== null && win.currentTab === 3
                onTriggered: win.goTab(3)
            }
            MenuSpec {
                text: qsTr("Folders"); shortcut: "Ctrl+5"; bindKey: true
                checkable: true; checked: win !== null && win.currentTab === 4
                onTriggered: win.goTab(4)
            }
            MenuSpec {
                text: qsTr("Private Album")
                enabled: !app.editing && privateAlbum.supported
                onTriggered: win.openPrivateAlbum()
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Thumbnail Size")
                submenu: true
                model: [2, 3, 4, 5, 6, 7, 8, 10, 12].map(n => ({ text: qsTr("%1 columns").arg(n), value: n, checked: prefs.columns === n }))
                onPicked: (value) => prefs.columns = value
                MenuSpec { text: qsTr("Bigger"); shortcut: "Ctrl++"; enabled: prefs.columns > prefs.minColumns; onTriggered: prefs.columns = prefs.columns - 1 }
                MenuSpec { text: qsTr("Smaller"); shortcut: "Ctrl+-"; enabled: prefs.columns < prefs.maxColumns; onTriggered: prefs.columns = prefs.columns + 1 }
                MenuSpec { separator: true }
            }
            MenuSpec {
                text: qsTr("Sort")
                MenuSpec { text: qsTr("Newest First"); checkable: true; checked: !prefs.sortAscending; onTriggered: prefs.sortAscending = false }
                MenuSpec { text: qsTr("Oldest First"); checkable: true; checked: prefs.sortAscending; onTriggered: prefs.sortAscending = true }
            }
            MenuSpec {
                text: qsTr("Theme")
                MenuSpec { text: qsTr("Follow System"); checkable: true; checked: prefs.theme === "system"; onTriggered: prefs.theme = "system" }
                MenuSpec { text: qsTr("Light"); checkable: true; checked: prefs.theme === "light"; onTriggered: prefs.theme = "light" }
                MenuSpec { text: qsTr("Dark"); checkable: true; checked: prefs.theme === "dark"; onTriggered: prefs.theme = "dark" }
            }
            MenuSpec {
                text: qsTr("Colour Style")
                MenuSpec { text: qsTr("Black && White"); checkable: true; checked: prefs.colorStyle === "neutral"; onTriggered: prefs.colorStyle = "neutral" }
                MenuSpec { text: qsTr("Material You (from the accent colour)"); checkable: true; checked: prefs.colorStyle === "tinted"; onTriggered: prefs.colorStyle = "tinted" }
            }
            MenuSpec {
                text: qsTr("Navigation Bar")
                MenuSpec { text: qsTr("Solid"); checkable: true; checked: prefs.navStyle === "solid"; onTriggered: prefs.navStyle = "solid" }
                MenuSpec { text: qsTr("Frosted Glass"); checkable: true; checked: prefs.navStyle === "frosted"; onTriggered: prefs.navStyle = "frosted" }
                MenuSpec { text: qsTr("Clear Glass"); checkable: true; checked: prefs.navStyle === "clear"; onTriggered: prefs.navStyle = "clear" }
            }
            MenuSpec {
                text: qsTr("Accent Colour")
                submenu: true
                model: [{ text: qsTr("System (KDE accent colour)"), value: "system", checked: prefs.accent === "system" }]
                       .concat(Theme.accentPalette.map(p => ({ text: p.name, value: p.color, checked: prefs.accent === p.color })))
                onPicked: (value) => prefs.accent = value
                dynamicFirst: true
                MenuSpec { separator: true }
                MenuSpec { text: qsTr("Custom…"); onTriggered: win.pickCustomAccent() }
            }
            MenuSpec {
                text: qsTr("Albums per Sub-folder")
                checkable: true; checked: prefs.albumsBySubfolder
                onTriggered: prefs.albumsBySubfolder = !prefs.albumsBySubfolder
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Play Video"); shortcut: "Return"
                visible: app.viewing && app.viewer.isVideo
                enabled: app.viewing && app.viewer.isVideo
                onTriggered: app.viewer.playCurrent()
            }
            MenuSpec {
                text: qsTr("Mute Preview"); shortcut: "M"
                visible: app.viewing && app.viewer.isVideo
                checkable: true; checked: app.viewing && app.viewer.videoMuted
                onTriggered: app.viewer.toggleMute()
            }
            MenuSpec {
                text: qsTr("Capture Frame"); shortcut: "S"
                visible: app.viewing && app.viewer.isVideo
                enabled: app.viewing && app.viewer.isVideo && gallery.videoThumbnailsSupported && !app.inPrivate
                onTriggered: app.viewer.captureFrame()
            }
            MenuSpec { separator: true; visible: app.viewing && app.viewer.isVideo }
            MenuSpec { text: qsTr("Zoom In"); shortcut: "+"; enabled: app.viewing; onTriggered: app.viewer.zoomStep(1.5) }
            MenuSpec { text: qsTr("Zoom Out"); shortcut: "-"; enabled: app.viewing; onTriggered: app.viewer.zoomStep(1 / 1.5) }
            MenuSpec { text: qsTr("Fit to Window"); shortcut: "0"; enabled: app.viewing; onTriggered: app.viewer.fit() }
            MenuSpec {
                text: qsTr("Show Details"); shortcut: "I"
                checkable: true; checked: app.viewing && app.viewer.detailsOpen
                enabled: app.viewing
                onTriggered: app.viewer.detailsOpen = !app.viewer.detailsOpen
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Full Screen"); shortcut: "F11"; bindKey: true
                checkable: true; checked: win !== null && win.visibility === Window.FullScreen
                onTriggered: win.toggleFullScreen()
            }
        },

        MenuSpec {
            text: qsTr("&Go")
            MenuSpec { text: qsTr("Back"); shortcut: "Alt+Left"; enabled: win !== null && win.canGoBack; onTriggered: win.goBack() }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Previous Picture"); shortcut: "Left"
                enabled: app.viewing && app.viewer.currentIndex > 0
                onTriggered: app.viewer.go(-1)
            }
            MenuSpec {
                text: qsTr("Next Picture"); shortcut: "Right"
                enabled: app.viewing && app.viewer.photoModel !== null && app.viewer.currentIndex < app.viewer.photoModel.itemCount - 1
                onTriggered: app.viewer.go(1)
            }
            MenuSpec { text: qsTr("First Picture"); shortcut: "Home"; enabled: app.viewing; onTriggered: app.viewer.goTo(0) }
            MenuSpec {
                text: qsTr("Last Picture"); shortcut: "End"; enabled: app.viewing
                onTriggered: app.viewer.goTo(app.viewer.photoModel.itemCount - 1)
            }
            MenuSpec { separator: true }
            MenuSpec {
                text: qsTr("Today"); shortcut: "Ctrl+Home"; bindKey: true
                enabled: !app.viewing && !app.editing && photos.itemCount > 0
                onTriggered: app.goToToday()
            }
            MenuSpec {
                text: qsTr("Jump to Year")
                submenu: true
                enabled: !app.viewing && !app.editing && photos.itemCount > 0
                model: photos.itemCount >= 0 ? photos.years().map(y => ({ text: String(y), value: y })) : []
                onPicked: (value) => app.jumpToYear(value)
            }
            MenuSpec {
                text: qsTr("Albums")
                submenu: true
                enabled: !app.editing && albums.count > 0
                model: albums.entries.map(a => ({ text: a.kind === "private" ? a.title : a.title + "  ·  " + a.count, value: a }))
                onPicked: (value) => { if (app.viewing) app.viewer.close(); win.openAlbum(value.kind, value.key, value.title) }
            }
            MenuSpec {
                text: qsTr("Stories")
                submenu: true
                enabled: !app.editing && collections.stories.length > 0
                model: collections.stories.map(st => ({ text: st.title + "  ·  " + st.subtitle, value: st }))
                onPicked: (value) => { if (app.viewing) app.viewer.close(); win.playStory(value) }
            }
            MenuSpec {
                text: qsTr("People")
                enabled: !app.editing
                onTriggered: { if (app.viewing) app.viewer.close(); win.goTab(3); win.openPeople() }
            }
            MenuSpec {
                text: qsTr("Places")
                enabled: !app.editing
                onTriggered: { if (app.viewing) app.viewer.close(); win.goTab(3); win.openPlaces() }
            }
            MenuSpec {
                text: qsTr("Favorites")
                enabled: !app.editing
                onTriggered: { if (app.viewing) app.viewer.close(); win.openAlbum("favorites", "", qsTr("Favorites")) }
            }
            MenuSpec { separator: true }
            MenuSpec { text: qsTr("Search"); shortcut: "Ctrl+F"; enabled: !app.viewing && !app.editing; onTriggered: win.openSearch() }
        },

        MenuSpec {
            text: qsTr("&Settings")
            // in the ⋮ menu, Settings is the gear in the nav bar instead
            MenuSpec { text: qsTr("Settings…"); shortcut: "Ctrl+,"; inPopup: false; enabled: !app.editing; onTriggered: { if (app.viewing) app.viewer.close(); win.openSettings() } }
            MenuSpec { separator: true; inPopup: false }
            MenuSpec {
                text: qsTr("Live Updates")
                checkable: true; checked: prefs.liveUpdates && gallery.liveUpdatesSupported
                enabled: gallery.liveUpdatesSupported
                onTriggered: prefs.liveUpdates = !prefs.liveUpdates
            }
            MenuSpec {
                text: gallery.defaultViewer === "default" ? qsTr("One Gallery Is the Default Image Viewer") : qsTr("Set as Default Image Viewer")
                enabled: gallery.defaultViewer === "other" || gallery.defaultViewer === "partial"
                onTriggered: gallery.setAsDefaultViewer()
            }
            MenuSpec {
                text: qsTr("Group Faces (People)")
                checkable: true; checked: prefs.facesEnabled
                enabled: collections.peopleState !== "unavailable"
                onTriggered: prefs.facesEnabled ? collections.disablePeople(false) : collections.enablePeople()
            }
            MenuSpec { text: qsTr("Clear Thumbnail Cache"); onTriggered: gallery.clearThumbnailCache() }
        },

        MenuSpec {
            text: qsTr("&Help")
            MenuSpec { text: qsTr("Keyboard Shortcuts"); shortcut: "Ctrl+F1"; bindKey: true; onTriggered: win.showShortcuts() }
            MenuSpec { text: qsTr("Project Page"); onTriggered: Qt.openUrlExternally(gallery.projectUrl) }
            MenuSpec { text: qsTr("Report a Problem"); onTriggered: Qt.openUrlExternally(gallery.projectUrl + "/issues") }
            MenuSpec { separator: true }
            MenuSpec { text: qsTr("About One Gallery"); onTriggered: win.showAbout() }
        }
    ]
}
