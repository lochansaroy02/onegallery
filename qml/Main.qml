import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Window
import QtCore
import "."
import "components"
import "menu"

ApplicationWindow {
    id: root
    width: 1200
    height: 820
    minimumWidth: 440
    minimumHeight: 520
    visible: true
    title: qsTr("One Gallery")
    color: Theme.bg
    font.family: Theme.fontFamily

    Binding {
        target: Theme
        property: "dark"
        value: prefs.theme === "dark" || (prefs.theme === "system" && gallery.systemDark)
    }
    // accent: KDE's accent colour (System Settings > Colors & Themes > Colors) or a chosen one
    readonly property color systemAccent: gallery.systemAccent !== "" ? gallery.systemAccent : Theme.defaultAccent
    Binding {
        target: Theme
        property: "seedColor"
        value: prefs.accent === "system" ? root.systemAccent : prefs.accent
    }
    // Black & white (One UI) or Material You (the whole palette from the accent)
    Binding {
        target: Theme
        property: "colorStyle"
        value: prefs.colorStyle
    }
    function pickCustomAccent() {
        accentDialog.selectedColor = Theme.seedColor
        accentDialog.open()
    }

    readonly property real navInset: Theme.navHeight + Theme.s5 * 2
    readonly property var currentGrid: stack.currentItem && stack.currentItem.grid ? stack.currentItem.grid : null
    readonly property bool dialogOpen: confirmDialog.opened || openWithPopup.opened || shareMenu.opened
                                       || shortcutsDialog.opened || aboutDialog.opened || appPopup.opened
                                       || nameDialog.opened || mergeDialog.opened || excludeDialog.opened
                                       || printDialog.opened || passwordDialog.opened
    readonly property var videoPlayer: videoPlayerLoader.item
    readonly property bool playingVideo: videoPlayer !== null && videoPlayer.visible
    readonly property bool editing: editorPage.visible || storyPlayer.visible || playingVideo
    // started by "Open with Gallery": closing the viewer quits instead of showing the library
    property bool standalone: launchedWithFiles
    property string externalFocus: ""
    property var tabsItem: null
    readonly property int currentTab: tabsItem ? tabsItem.current : 0
    readonly property bool canGoBack: editorPage.visible || viewer.visible || playingVideo
                                      || (currentGrid !== null && currentGrid.selectMode) || stack.depth > 1

    // ---- API used by the views (via ApplicationWindow.window) -----------------------
    function openViewer(grid, index) { viewer.open(grid, index) }
    function openEditor(info) { editorPage.open(info) }
    function printPicture(info) {
        if (info && info.path && info.video !== true) printDialog.openFor(info)
    }
    // the built-in video player, continuing from the inline preview's position
    function playVideo(info, startMs) {
        if (!info || !info.path) return
        if (videoPlayer === null) {   // Qt Multimedia missing
            gallery.openExternally(info.path)
            return
        }
        videoPlayer.open(info, startMs || 0)
    }
    // 75000 -> "1:15", 3723000 -> "1:02:03"
    function formatTime(ms) {
        var s = Math.max(0, Math.floor((ms || 0) / 1000))
        var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
        var mm = h > 0 && m < 10 ? "0" + m : "" + m
        return (h > 0 ? h + ":" : "") + mm + ":" + (sec < 10 ? "0" : "") + sec
    }
    function raiseWindow() {
        if (root.visibility === Window.Minimized) root.showNormal()
        root.raise()
        root.requestActivate()
    }
    function goTab(index) {
        if (editorPage.visible) return
        if (playingVideo) videoPlayer.close()
        if (viewer.visible) viewer.close()
        if (stack.depth > 1) stack.pop(null)
        if (tabsItem) tabsItem.current = index
    }
    function toggleFullScreen() {
        if (root.visibility === Window.FullScreen) root.showNormal()
        else root.showFullScreen()
    }
    function openPictureDialog() { openPicture.open() }
    function showShortcuts() { shortcutsDialog.open() }
    function showAbout() { aboutDialog.open() }
    function editExcludes(rootPath, excludes) { excludeDialog.openFor(rootPath, excludes || []) }
    function openAppMenu(anchor) {
        appPopup.popup(anchor, anchor.width - appPopup.implicitWidth, anchor.height)
    }
    function showLibrary() {
        // "Open Gallery" from a picture that was opened from the file manager
        standalone = false
        viewer.close()
    }
    function openWith(paths) {
        if (!paths.length) return
        if (gallery.isWindows) gallery.openWithDialog(paths[0])   // Windows' own chooser
        else openWithPopup.show(paths)
    }
    function share(paths, anchor, done) { if (paths.length) shareMenu.openFor(paths, anchor, done) }
    function addFolder() { folderDialog.open() }
    function showToast(message) { toast.show(message) }
    function confirm(title, message, action, callback) {
        confirmDialog.ask(title, message, action, callback, true)
    }
    function confirmDelete(paths, done) {
        if (!paths.length) return
        confirmDialog.ask(
            paths.length === 1 ? qsTr("Move this picture to the trash?")
                               : qsTr("Move %1 pictures to the trash?").arg(paths.length),
            qsTr("You can restore them from the Trash in Dolphin."),
            qsTr("Move to trash"),
            function() { gallery.trash(paths); if (done) done() }, true)
    }
    // ---- private album -------------------------------------------------------------------------
    readonly property bool privateOpen: stack.currentItem !== null && stack.currentItem.isPrivate === true
    function withPrivateAlbum(action) {
        if (!privateAlbum.supported) {
            toast.show(qsTr("The private album needs python-cryptography (sudo pacman -S python-cryptography)"))
            return
        }
        if (!privateAlbum.exists) passwordDialog.ask("create", action)
        else if (!privateAlbum.unlocked) passwordDialog.ask("unlock", action)
        else action()
    }
    function openPrivateAlbum() {
        withPrivateAlbum(function() {
            if (viewer.visible) viewer.close()
            if (!root.privateOpen) stack.push(privatePage)
        })
    }
    function moveToPrivate(paths, done) {
        paths = paths.filter(p => p && p.indexOf("private:") !== 0)
        if (!paths.length) return
        const wasLocked = !privateAlbum.unlocked && !root.privateOpen
        withPrivateAlbum(function() {
            confirmDialog.ask(
                paths.length === 1 ? qsTr("Move to the private album?")
                                   : qsTr("Move %1 items to the private album?").arg(paths.length),
                qsTr("They are encrypted and removed from their folder, so other apps and people using this computer can't see them. You can move them out again from the private album."),
                qsTr("Move"),
                function() { privateAlbum.moveIn(paths, wasLocked); if (done) done() }, false)
        })
    }
    function changePrivatePassword() { passwordDialog.ask("change", null) }
    function moveOutOfPrivate(ids, done) {
        if (!ids.length) return
        privateAlbum.moveOut(ids)
        if (done) done()
    }
    function deletePrivate(ids, done) {
        if (!ids.length) return
        confirmDialog.ask(
            ids.length === 1 ? qsTr("Delete permanently?") : qsTr("Delete %1 items permanently?").arg(ids.length),
            qsTr("They are deleted from the private album right away. They don't go to the trash and can't be restored."),
            qsTr("Delete"),
            function() { privateAlbum.deleteItems(ids); if (done) done() }, true)
    }
    // leave and lock the private album (Lock button, minimising the window)
    function closePrivateAlbum() {
        if (playingVideo && videoPlayer.info.private) videoPlayer.close()
        if (viewer.visible && viewer.info.private) viewer.close()
        if (stack.find(function(item) { return item.isPrivate === true }) !== null) stack.pop(null)
        privateAlbum.lock()
    }

    function openAlbum(kind, key, title) {
        if (kind === "private") { openPrivateAlbum(); return }
        albumPhotos.setFilter(kind, key)
        stack.push(albumPage, { title: title })
    }
    function openPerson(personId, name) {
        if (stack.currentItem && stack.currentItem.personId !== undefined && stack.currentItem.personId >= 0)
            stack.pop()
        albumPhotos.setFilter("person", String(personId))
        stack.push(albumPage, { title: name || qsTr("Add a name"), personId: personId })
    }
    function openPlace(key, name) {
        albumPhotos.setFilter("place", key)
        stack.push(albumPage, { title: name })
    }
    function openPeople() { stack.push(peoplePage) }
    function openPlaces() { stack.push(placesPage) }
    function playStory(story) { storyPlayer.play(story) }
    // show a library picture in the viewer (from a story)
    function openLibraryPicture(path) {
        goTab(0)
        Qt.callLater(function() {
            var index = photos.indexOfPath(path)
            if (index >= 0 && root.currentGrid) {
                root.currentGrid.ensureVisible(index)
                viewer.open(root.currentGrid, index)
            } else {
                gallery.openFiles([path])
            }
        })
    }
    function openSearch() {
        if (!(stack.currentItem && stack.currentItem.isSearch)) stack.push(searchPage)
    }
    readonly property int settingsTab: 5
    property var settingsView: null
    function openSettings() { goTab(settingsTab) }
    function goBack() {
        if (playingVideo) videoPlayer.dismiss()
        else if (storyPlayer.visible) storyPlayer.close()
        else if (editorPage.visible) editorPage.requestClose()
        else if (viewer.visible) viewer.close()
        else if (currentGrid && currentGrid.selectMode) currentGrid.exitSelection()
        else if (stack.depth > 1) stack.pop()
    }

    StackView {
        id: stack
        anchors.fill: parent
        initialItem: tabsPage

        pushEnter: Transition {
            NumberAnimation { property: "x"; from: stack.width * 0.08; to: 0; duration: Theme.durSlow; easing.type: Theme.easing }
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durNormal }
        }
        pushExit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durNormal }
        }
        popEnter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durNormal }
        }
        popExit: Transition {
            NumberAnimation { property: "x"; from: 0; to: stack.width * 0.08; duration: Theme.durNormal; easing.type: Theme.easing }
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durNormal }
        }
    }

    Component {
        id: tabsPage
        Item {
            id: tabs
            property int current: 0
            readonly property var grid: current === 0 ? pictures : current === 1 ? videosTab : null
            Component.onCompleted: root.tabsItem = tabs

            component Tab: Item {
                property int tabIndex
                anchors.fill: parent
                opacity: tabs.current === tabIndex ? 1 : 0
                visible: opacity > 0
                transform: Translate { y: tabs.current === tabIndex ? 0 : 16; Behavior on y { NumberAnimation { duration: Theme.durNormal; easing.type: Theme.easing } } }
                Behavior on opacity { NumberAnimation { duration: Theme.durNormal } }
            }

            // the pages under the nav bar: what its Liquid Glass shows through
            Item {
                id: tabContent
                anchors.fill: parent
                // same colour as the window: gives the glass an opaque picture of the page
                Rectangle { anchors.fill: parent; color: Theme.bg }

                Tab {
                    tabIndex: 0
                    PicturesView {
                        id: pictures
                        anchors.fill: parent
                        bottomInset: root.navInset
                        onSearchRequested: root.openSearch()
                        onSettingsRequested: root.openSettings()
                    }
                }
                Tab {
                    tabIndex: 1
                    VideosView {
                        id: videosTab
                        anchors.fill: parent
                        bottomInset: root.navInset
                        onSearchRequested: root.openSearch()
                        onSettingsRequested: root.openSettings()
                    }
                }
                Tab {
                    tabIndex: 2
                    AlbumsView {
                        anchors.fill: parent
                        bottomInset: root.navInset
                        onOpenAlbum: (kind, key, title) => root.openAlbum(kind, key, title)
                        onSearchRequested: root.openSearch()
                        onSettingsRequested: root.openSettings()
                    }
                }
                Tab {
                    tabIndex: 3
                    CollectionsView {
                        anchors.fill: parent
                        bottomInset: root.navInset
                        onPlayStory: (story) => root.playStory(story)
                        onOpenPeople: root.openPeople()
                        onOpenPlaces: root.openPlaces()
                        onOpenPerson: (personId, name) => root.openPerson(personId, name)
                        onOpenPlace: (key, name) => root.openPlace(key, name)
                    }
                }
                Tab {
                    tabIndex: 4
                    FoldersView {
                        anchors.fill: parent
                        bottomInset: root.navInset
                        onSettingsRequested: root.openSettings()
                    }
                }
                Tab {
                    tabIndex: 5
                    SettingsView {
                        anchors.fill: parent
                        Component.onCompleted: root.settingsView = this
                        showBack: false
                        bottomInset: root.navInset
                    }
                }
            }

            PillNav {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: tabs.grid && tabs.grid.selectMode ? -height - 20 : Theme.s5
                Behavior on anchors.bottomMargin { NumberAnimation { duration: Theme.durNormal; easing.type: Theme.easing } }
                maxWidth: tabs.width - 2 * Theme.s4
                glass: prefs.navStyle
                backdrop: tabContent
                currentIndex: tabs.current
                onSelected: (i) => tabs.current = i
            }
        }
    }

    Component {
        id: albumPage
        PhotoGrid {
            id: albumGrid
            readonly property var grid: albumGrid
            property int personId: -1
            readonly property bool personHidden: collections.hiddenPeople.some(p => p.id === personId)
            photoModel: albumPhotos
            showBack: true
            onBackRequested: stack.pop()
            onSearchRequested: root.openSearch()
            StackView.onRemoved: albumPhotos.setFilter("none", "")
            extraActions: personId < 0 ? [] : [
                { id: "name", icon: "edit", tip: qsTr("Name this person") },
                { id: "merge", icon: "merge", tip: qsTr("Same person as…") },
                personHidden ? { id: "unhide", icon: "eye", tip: qsTr("Show this person again") }
                             : { id: "hide", icon: "eyeOff", tip: qsTr("Hide this person") }
            ]
            onExtraAction: (id) => {
                const pid = albumGrid.personId
                if (id === "name") {
                    nameDialog.ask(collections.personName(pid), function(name) {
                        collections.renamePerson(pid, name)
                        albumGrid.title = name || qsTr("Add a name")
                    })
                } else if (id === "merge") {
                    mergeDialog.ask(pid, function(target) {
                        collections.mergePeople(pid, target)
                        stack.pop()
                        toast.show(qsTr("Pictures combined"))
                    })
                } else if (id === "hide") {
                    collections.setPersonHidden(pid, true)
                    stack.pop()
                    toast.show(qsTr("Person hidden. Show hidden people from the People page."))
                } else if (id === "unhide") {
                    collections.setPersonHidden(pid, false)
                }
            }
        }
    }

    Component {
        id: privatePage
        PhotoGrid {
            id: privateGrid
            readonly property var grid: privateGrid
            readonly property bool isPrivate: true
            photoModel: privatePhotos
            title: qsTr("Private album")
            showBack: true
            busy: privateAlbum.busy
            extraActions: [{ id: "lock", icon: "lock", tip: qsTr("Lock the private album") }]
            onExtraAction: (id) => { if (id === "lock") root.closePrivateAlbum() }
            onBackRequested: stack.pop()
            onSearchRequested: root.openSearch()
            StackView.onRemoved: privateAlbum.lock()
            emptyState: Component {
                Column {
                    spacing: Theme.s3
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 96
                        height: 96
                        radius: 48
                        color: Theme.accentSoft
                        Icon { anchors.centerIn: parent; name: "lock"; color: Theme.accent; size: 42 }
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: qsTr("Nothing here yet")
                        color: Theme.text
                        font.pixelSize: Theme.fontTitle
                        font.weight: Font.Bold
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: qsTr("Select pictures or videos and choose Private (or press Ctrl+Shift+H). They are encrypted and only open with your password.")
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontBody
                    }
                }
            }
        }
    }

    Component {
        id: searchPage
        SearchPage {
            id: search
            readonly property var grid: search
            readonly property bool isSearch: true
            onBackRequested: stack.pop()
            StackView.onRemoved: searchPhotos.setFilter("none", "")
        }
    }

    Component {
        id: peoplePage
        PeoplePage {
            onBackRequested: stack.pop()
            onOpenPerson: (personId, name) => root.openPerson(personId, name)
        }
    }
    Component {
        id: placesPage
        PlacesPage {
            onBackRequested: stack.pop()
            onOpenPlace: (key, name) => root.openPlace(key, name)
        }
    }

    ViewerPage {
        id: viewer
        anchors.fill: parent
        z: 100
        playerOpen: root.playingVideo
    }

    // separate file behind a Loader: without Qt Multimedia the rest of Gallery still works
    Loader {
        id: videoPlayerLoader
        anchors.fill: parent
        z: 110
        source: "VideoPlayer.qml"
        onStatusChanged: if (status === Loader.Error) console.warn("Video playback unavailable: install qt6-multimedia")
    }
    Connections {
        target: root.videoPlayer
        function onClosed(position) {
            viewer.resumeFrom(viewer.info.path || "", position)
            viewer.forceActiveFocus()
        }
    }

    EditorPage {
        id: editorPage
        anchors.fill: parent
        z: 150
        onFinished: (path) => viewer.follow(path)
    }

    StoryPlayer {
        id: storyPlayer
        anchors.fill: parent
        z: 120
        onOpenPicture: (path) => root.openLibraryPicture(path)
    }

    Toast {
        id: toast
        z: 200
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.navInset + Theme.s3
    }

    // ---- application menu: KDE global menu + the in-app ⋮ menu ----------------------------
    AppMenuModel {
        id: appMenu
        win: root
        viewer: viewer
        editorPage: editorPage
    }
    // only where a global menu is running (otherwise Qt has no native menu bar to fill)
    Loader {
        active: gallery.globalMenuAvailable
        sourceComponent: Component { GlobalMenuBar { specs: appMenu.menus; window: root } }
    }
    AppPopupMenu { id: appPopup; specs: appMenu.menus }
    ShortcutsDialog { id: shortcutsDialog }
    NameDialog { id: nameDialog }
    ExcludeFoldersDialog { id: excludeDialog }
    MergeDialog { id: mergeDialog }
    AboutDialog { id: aboutDialog }
    PasswordDialog { id: passwordDialog }
    PrintDialog { id: printDialog }

    ColorDialog {
        id: accentDialog
        title: qsTr("Choose an accent colour")
        onAccepted: prefs.accent = selectedColor.toString().slice(0, 7)
    }

    FileDialog {
        id: openPicture
        title: qsTr("Open pictures")
        fileMode: FileDialog.OpenFiles
        currentFolder: StandardPaths.writableLocation(StandardPaths.PicturesLocation)
        nameFilters: [qsTr("Pictures and videos (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff *.heic *.heif *.mp4 *.m4v *.mov *.mkv *.webm *.avi *.3gp *.mts *.m2ts *.wmv *.ogv *.mpg *.mpeg)"),
                      qsTr("Pictures (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff *.heic *.heif)"),
                      qsTr("Videos (*.mp4 *.m4v *.mov *.mkv *.webm *.avi *.3gp *.mts *.m2ts *.wmv *.ogv *.mpg *.mpeg)"),
                      qsTr("All files (*)")]
        onAccepted: gallery.openFiles(selectedFiles.map(u => u.toString()))
    }

    // keep the Share submenu ready for the current selection
    Connections {
        target: root.currentGrid ? root.currentGrid.photoModel : null
        function onSelectionChanged() {
            const model = root.currentGrid.photoModel
            if (model.selectionCount > 0) gallery.prepareShare(model.selectedPaths().slice(0, 20))
        }
    }

    Component.onCompleted: {
        appMenu.installShortcuts(root.contentItem)
        gallery.refreshDefaultViewer()
    }

    ConfirmDialog { id: confirmDialog }
    OpenWithPopup { id: openWithPopup }
    ShareMenu { id: shareMenu }

    FolderDialog {
        id: folderDialog
        title: qsTr("Choose a folder to show in the gallery")
        currentFolder: StandardPaths.writableLocation(StandardPaths.PicturesLocation)
        onAccepted: gallery.addFolder(selectedFolder.toString())
    }

    Connections {
        target: gallery
        function onToast(message) { toast.show(message) }
        function onActivateRequested() { root.raiseWindow() }
        function onExternalOpenRequested(path) {
            if (editorPage.visible) editorPage.close()
            if (viewer.visible && viewer.photoModel === externalPhotos) {
                viewer.follow(path)          // already browsing outside files: jump there
            } else {
                root.externalFocus = path
                viewer.showBlank()           // black screen until the folder is listed
            }
            root.raiseWindow()
        }
    }

    // a stand-in "grid" for pictures that are not in the library
    QtObject {
        id: externalGrid
        readonly property var photoModel: externalPhotos
        property bool selectMode: false
        function rectForItem(index) { return null }
        function ensureVisible(index) { }
    }
    Connections {
        target: externalPhotos
        function onViewReset() {
            if (root.externalFocus === "") return
            var idx = externalPhotos.indexOfPath(root.externalFocus)
            if (idx < 0) return
            root.externalFocus = ""
            viewer.open(externalGrid, idx)
        }
    }
    // lock the private album when the window is minimised
    onVisibilityChanged: (v) => { if (v === Window.Minimized && privateAlbum.unlocked) closePrivateAlbum() }
    Connections {
        target: privateAlbum
        function onStateChanged() {
            if (!privateAlbum.unlocked && root.playingVideo && root.videoPlayer.info.private) root.videoPlayer.close()
        }
    }

    Connections {
        target: viewer
        function onVisibleChanged() {
            if (!viewer.visible && root.standalone) Qt.quit()
        }
    }

    // ---- keyboard ---------------------------------------------------------------------
    Shortcut {
        sequence: "Esc"
        enabled: !root.dialogOpen
        onActivated: root.goBack()
    }
    Shortcut {
        sequences: [StandardKey.Back]
        enabled: !root.dialogOpen && !viewer.visible
        onActivated: root.goBack()
    }
    Shortcut {
        sequences: [StandardKey.Find]
        enabled: !root.editing && !viewer.visible && !root.dialogOpen
        onActivated: root.openSearch()
    }
    Shortcut {
        sequence: "F5"
        enabled: !root.editing
        onActivated: gallery.rescan()
    }
    Shortcut {
        sequence: "Ctrl+O"
        enabled: !root.editing && !viewer.visible
        onActivated: root.addFolder()
    }
    Shortcut {
        sequences: [StandardKey.Preferences]
        enabled: !viewer.visible && !root.editing
        onActivated: root.openSettings()
    }
    Shortcut {
        sequence: "Ctrl+,"
        enabled: !viewer.visible && !root.editing
        onActivated: root.openSettings()
    }
    Shortcut {
        sequences: [StandardKey.SelectAll]
        enabled: !root.editing && !viewer.visible && root.currentGrid !== null && !root.dialogOpen
        onActivated: { root.currentGrid.selectMode = true; root.currentGrid.photoModel.selectAll() }
    }
    Shortcut {
        sequences: [StandardKey.Delete]
        enabled: !root.dialogOpen && !root.editing
        onActivated: {
            if (viewer.visible) viewer.deleteCurrent()
            else if (root.currentGrid && root.currentGrid.selectMode)
                root.confirmDelete(root.currentGrid.photoModel.selectedPaths(),
                                   function() { root.currentGrid.exitSelection() })
        }
    }
    Shortcut {
        sequences: [StandardKey.ZoomIn, "Ctrl+="]
        enabled: !root.editing && !viewer.visible && root.currentGrid !== null
        onActivated: root.currentGrid.changeColumns(-1)
    }
    Shortcut {
        sequences: [StandardKey.ZoomOut]
        enabled: !root.editing && !viewer.visible && root.currentGrid !== null
        onActivated: root.currentGrid.changeColumns(1)
    }
}
