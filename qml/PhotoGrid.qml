import QtQuick
import QtQuick.Controls
import "."
import "components"

// Date-grouped thumbnail grid with collapsing header, sticky day headers,
// fast scroller and selection mode. Used by Pictures, album pages and search.
Item {
    id: grid
    required property var photoModel
    property string title: qsTr("One Gallery")
    property string subtitle: countText(photoModel.itemCount)
    property bool busy: false
    property bool showBack: false
    property bool bigHeader: true
    property bool showSearchButton: true
    property bool showSettingsButton: false
    property Component barMiddle: null
    property Component emptyState: null
    property real bottomInset: 0
    property bool selectMode: false
    property var extraActions: []          // [{id, icon, tip}] shown in the header
    readonly property alias view: list
    signal backRequested()
    signal searchRequested()
    signal settingsRequested()
    signal extraAction(string id)

    readonly property int columns: Math.max(1, photoModel.columns)
    readonly property real cellSize: Math.max(24, Math.floor((list.width - Theme.gridGap * (columns - 1)) / columns))
    // the big title area. With the empty-state message on a short window there is no room
    // for both: the big title then folds into the top bar, as One UI does.
    readonly property real emptyNeed: emptyLoader.active && emptyLoader.item ? emptyLoader.item.implicitHeight + Theme.s5 : 0
    readonly property real fullHeader: Math.max(150, Math.min(250, height * 0.3))
    readonly property real roomForHeader: height - bottomInset - Theme.barHeight - emptyNeed
    readonly property real headerHeight: !bigHeader ? 0
        : emptyNeed <= 0 ? fullHeader
        : roomForHeader >= 150 ? Math.min(fullHeader, roomForHeader) : 0
    readonly property real collapse: bigHeader && headerHeight > 0
        ? Math.max(0, Math.min(1, (list.contentY - list.originY) / (headerHeight * 0.7))) : 1
    readonly property string selectionText: photoModel.selectionCount === 0
        ? qsTr("Select items") : qsTr("%1 selected").arg(photoModel.selectionCount)

    function countText(n) {
        function num(k) { return k.toLocaleString(Qt.locale(), "f", 0) }
        var v = Math.min(n, photoModel.videoCount)
        var p = n - v
        var pictures = p === 1 ? qsTr("1 picture") : qsTr("%1 pictures").arg(num(p))
        if (v === 0) return pictures
        var vids = v === 1 ? qsTr("1 video") : qsTr("%1 videos").arg(num(v))
        return p === 0 ? vids : pictures + "  ·  " + vids
    }
    function enterSelection(index) {
        selectMode = true
        if (index >= 0 && !photoModel.itemAt(index).selected)
            photoModel.toggleSelected(index)
    }
    function exitSelection() {
        selectMode = false
        photoModel.clearSelection()
    }
    function changeColumns(delta) {
        prefs.columns = prefs.columns + delta
    }
    function activate(index, modifiers, thumbItem) {
        if (selectMode) {
            if (modifiers & Qt.ShiftModifier) photoModel.selectRangeTo(index)
            else photoModel.toggleSelected(index)
        } else if (modifiers & Qt.ControlModifier) {
            enterSelection(index)
        } else {
            ApplicationWindow.window.openViewer(grid, index)
        }
    }
    // Window-space rectangle of a visible thumbnail (for the viewer transition), or null.
    function rectForItem(index) {
        var row = photoModel.rowForItem(index)
        if (row < 0) return null
        var rowItem = list.itemAtIndex(row)
        if (!rowItem) return null
        var t = rowItem.thumbAt(index - photoModel.firstItemOfRow(row))
        if (!t) return null
        var p = t.mapToItem(list, 0, 0)
        if (p.y + t.height < Theme.sectionHeight || p.y > list.height) return null
        var w = t.mapToItem(null, 0, 0)
        return { x: w.x, y: w.y, width: t.width, height: t.height, src: t.item.src }
    }
    function ensureVisible(index) {
        var row = photoModel.rowForItem(index)
        if (row >= 0) list.positionViewAtIndex(row, ListView.Contain)
    }

    // keep the first visible picture in place when the model is rebuilt
    property int anchorId: -1
    Connections {
        target: grid.photoModel
        function onViewAboutToReset() {
            grid.anchorId = -1
            if (list.contentY - list.originY > grid.headerHeight) {
                var row = list.indexAt(20, list.contentY + Theme.sectionHeight + 4)
                if (row >= 0)
                    grid.anchorId = grid.photoModel.idAt(grid.photoModel.firstItemOfRow(row))
            }
        }
        function onViewReset() {
            if (grid.anchorId < 0) return
            var id = grid.anchorId
            Qt.callLater(function() {
                var idx = grid.photoModel.indexOfId(id)
                if (idx >= 0)
                    list.positionViewAtIndex(grid.photoModel.rowForItem(idx), ListView.Beginning)
            })
        }
    }

    CollapsingHeader {
        id: bar
        z: 2
        width: parent.width
        title: grid.selectMode ? grid.selectionText : grid.title
        progress: grid.selectMode ? 1 : grid.collapse
        showBack: grid.selectMode || grid.showBack
        backIcon: grid.selectMode ? "close" : "back"
        middle: grid.selectMode ? null : grid.barMiddle
        onBackClicked: grid.selectMode ? grid.exitSelection() : grid.backRequested()

        IconButton {
            visible: grid.selectMode
            icon: "selectAll"
            tip: qsTr("Select all (Ctrl+A)")
            color: grid.photoModel.selectionCount > 0 && grid.photoModel.selectionCount === grid.photoModel.itemCount
                   ? Theme.accent : Theme.text
            onClicked: grid.photoModel.selectionCount === grid.photoModel.itemCount
                       ? grid.photoModel.clearSelection() : grid.photoModel.selectAll()
        }
        Repeater {
            model: grid.selectMode ? [] : grid.extraActions
            delegate: IconButton {
                required property var modelData
                icon: modelData.icon
                tip: modelData.tip
                onClicked: grid.extraAction(modelData.id)
            }
        }
        IconButton {
            visible: !grid.selectMode && grid.photoModel.itemCount > 0
            icon: "zoomIn"
            tip: qsTr("Bigger thumbnails (Ctrl + / Ctrl + wheel)")
            enabled: prefs.columns > prefs.minColumns
            onClicked: grid.changeColumns(-1)
        }
        IconButton {
            visible: !grid.selectMode && grid.photoModel.itemCount > 0
            icon: "zoomOut"
            tip: qsTr("Smaller thumbnails (Ctrl -)")
            enabled: prefs.columns < prefs.maxColumns
            onClicked: grid.changeColumns(1)
        }
        IconButton {
            visible: !grid.selectMode && grid.showSearchButton
            icon: "search"
            tip: qsTr("Search (Ctrl+F)")
            onClicked: grid.searchRequested()
        }
        IconButton {
            visible: !grid.selectMode && grid.photoModel.itemCount > 0
            icon: "selectAll"
            tip: qsTr("Select")
            onClicked: grid.selectMode = true
        }
        IconButton {
            id: menuButton
            visible: !grid.selectMode && grid.showSettingsButton
            icon: "more"
            tip: qsTr("Menu")
            onClicked: ApplicationWindow.window.openAppMenu(menuButton)
        }
    }

    // indeterminate progress line while scanning
    Item {
        id: progressLine
        z: 3
        anchors.top: bar.bottom
        width: parent.width
        height: 2
        clip: true
        visible: grid.busy
        Rectangle {
            width: parent.width * 0.3
            height: 2
            radius: 1
            color: Theme.accent
            NumberAnimation on x {
                running: progressLine.visible
                from: -progressLine.width * 0.3
                to: progressLine.width
                duration: 1200
                loops: Animation.Infinite
                easing.type: Easing.InOutQuad
            }
        }
    }

    ListView {
        id: list
        anchors.top: bar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        model: grid.photoModel
        reuseItems: true
        cacheBuffer: Math.round(grid.cellSize * 4)
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 2500
        maximumFlickVelocity: 8000

        header: BigTitle {
            width: list.width
            height: grid.headerHeight
            visible: grid.bigHeader && height > 0
            title: grid.selectMode ? grid.selectionText : grid.title
            subtitle: grid.subtitle
            busy: grid.busy
            progress: grid.collapse
        }
        footer: Item { width: 1; height: grid.bottomInset + Theme.s4 }

        section.property: "day"
        section.criteria: ViewSection.FullString
        section.labelPositioning: ViewSection.InlineLabels | ViewSection.CurrentLabelAtStart
        section.delegate: SectionHeader {
            required property string section
            width: ListView.view ? ListView.view.width : 0
            label: grid.photoModel.dayLabel(section)
            level: grid.photoModel.groupBy
            selecting: grid.selectMode
            checked: grid.selectMode && grid.photoModel.selectionCount >= 0
                     && grid.photoModel.isDaySelected(section)
            onToggle: grid.photoModel.toggleDay(section)
        }

        delegate: Item {
            id: rowItem
            required property var rowItems
            required property int index
            width: list.width
            height: grid.cellSize + Theme.gridGap
            function thumbAt(column) { return rep.itemAt(column) }

            Row {
                x: Math.floor((list.width - (grid.cellSize * grid.columns + Theme.gridGap * (grid.columns - 1))) / 2)
                spacing: Theme.gridGap
                Repeater {
                    id: rep
                    model: rowItem.rowItems ? rowItem.rowItems.length : 0
                    delegate: Thumb {
                        required property int index
                        width: grid.cellSize
                        height: grid.cellSize
                        item: rowItem.rowItems[index] || ({})
                        selecting: grid.selectMode
                        onActivated: (i, mods) => grid.activate(i, mods, this)
                        onLongPressed: (i) => grid.enterSelection(i)
                        onContextRequested: (i) => {
                            if (grid.selectMode) grid.photoModel.toggleSelected(i)
                            else grid.enterSelection(i)
                        }
                    }
                }
            }
        }

        // Ctrl + wheel (and touchpad pinch) change the column count like pinch-to-zoom
        WheelHandler {
            target: null
            acceptedModifiers: Qt.ControlModifier
            property real acc: 0
            onWheel: (ev) => {
                acc += ev.angleDelta.y
                if (acc >= 120) { grid.changeColumns(-1); acc = 0 }
                else if (acc <= -120) { grid.changeColumns(1); acc = 0 }
            }
        }
        PinchHandler {
            target: null
            property real base: 1
            onActiveChanged: base = 1
            onActiveScaleChanged: {
                if (activeScale / base > 1.25) { grid.changeColumns(-1); base = activeScale }
                else if (activeScale / base < 0.8) { grid.changeColumns(1); base = activeScale }
            }
        }
    }

    // "Days" / "Months" / "Years" bubble when zooming switches the grouping
    Rectangle {
        id: zoomHint
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: bar.bottom
        anchors.topMargin: Theme.s4
        z: 10
        width: zoomHintText.implicitWidth + 2 * Theme.s5
        height: 36
        radius: 18
        color: Theme.toastBg
        opacity: 0
        visible: opacity > 0
        Text {
            id: zoomHintText
            anchors.centerIn: parent
            color: "white"
            font.pixelSize: Theme.fontBody
            font.weight: Font.DemiBold
            text: grid.photoModel.groupBy === "year" ? qsTr("Years")
                : grid.photoModel.groupBy === "month" ? qsTr("Months") : qsTr("Days")
        }
        SequentialAnimation {
            id: zoomHintAnim
            NumberAnimation { target: zoomHint; property: "opacity"; to: 0.92; duration: Theme.durFast }
            PauseAnimation { duration: 900 }
            NumberAnimation { target: zoomHint; property: "opacity"; to: 0; duration: Theme.durSlow }
        }
        Connections {
            target: grid.photoModel
            function onGroupByChanged() { if (grid.visible) zoomHintAnim.restart() }
        }
    }

    FastScroller {
        z: 2
        anchors.right: parent.right
        anchors.top: list.top
        anchors.topMargin: Theme.s2
        anchors.bottom: parent.bottom
        anchors.bottomMargin: grid.bottomInset + Theme.s2
        view: list
        labelForRow: function(row) { return grid.photoModel.monthLabelForRow(row) }
    }

    // empty state: below the big title (never over it), centred in the space that is left,
    // and scaled down a little when the window is too short for both
    Item {
        id: emptyArea
        anchors.top: list.top
        anchors.topMargin: grid.headerHeight + Theme.s2
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: grid.bottomInset
        visible: emptyLoader.active

        Loader {
            id: emptyLoader
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 460)
            active: grid.emptyState !== null && grid.photoModel.itemCount === 0 && !grid.photoModel.loading
            sourceComponent: grid.emptyState
            transformOrigin: Item.Top
            scale: item && item.implicitHeight > 0 ? Math.min(1, Math.max(0.75, parent.height / item.implicitHeight)) : 1
            // keep the top edge inside the area when scaled
            anchors.verticalCenterOffset: item && scale < 1 ? -(parent.height - height) / 2 : 0
        }
    }

    SelectionBar {
        z: 4
        photoModel: grid.photoModel
        anchors.horizontalCenter: parent.horizontalCenter
        y: grid.selectMode ? parent.height - height - Theme.s5 : parent.height + 20
        opacity: grid.selectMode ? 1 : 0
        visible: opacity > 0
        Behavior on y { NumberAnimation { duration: Theme.durNormal; easing.type: Theme.easing } }
        Behavior on opacity { NumberAnimation { duration: Theme.durNormal } }
        onFinished: grid.exitSelection()
    }
}
