// Windows-style live tile: a mosaic of pictures where one cell at a time flips over (in 3D,
// around its horizontal axis) to a picture that isn't showing yet. Every step of `index`
// (the slideshow timer, the ‹ › buttons, the wheel) flips one cell.
// Plain QtQuick (no Plasma imports), so it can also be rendered outside plasmashell.
import QtQuick
import QtQuick.Effects

Item {
    id: mosaic

    property var items: []            // [{image, path, title, subtitle}] from feed.json
    property int index: 0
    property bool showCaption: true
    property bool interactive: true
    property real radius: 20
    property real fontPixelSize: 13
    property real gap: 2

    readonly property bool hovered: hover.hovered

    signal activated(var item)
    signal next()
    signal previous()

    // cells as [column, row, columns spanned, rows spanned]; the first one is the big picture.
    // A layout needs at least one picture more than it has cells, to have something to flip in.
    readonly property var layout: {
        const aspect = width / Math.max(1, height)
        const count = items.length
        const layouts = aspect >= 1.25
            ? [{ cols: 3, rows: 2, cells: [[0, 0, 2, 2], [2, 0, 1, 1], [2, 1, 1, 1]] }]
            : aspect <= 0.8
            ? [{ cols: 2, rows: 3, cells: [[0, 0, 2, 2], [0, 2, 1, 1], [1, 2, 1, 1]] }]
            : [{ cols: 3, rows: 3, cells: [[0, 0, 2, 2], [2, 0, 1, 1], [2, 1, 1, 1],
                                           [0, 2, 1, 1], [1, 2, 1, 1], [2, 2, 1, 1]] },
               { cols: 2, rows: 2, cells: [[0, 0, 1, 1], [1, 0, 1, 1], [0, 1, 1, 1], [1, 1, 1, 1]] }]
        for (const l of layouts) {
            if (count > l.cells.length)
                return l
        }
        return { cols: 1, rows: 1, cells: [[0, 0, 1, 1]] }
    }

    function fileUrl(path) {
        return "file://" + path.split("/").map(encodeURIComponent).join("/")
    }

    property int _cursor: 0         // next picture to flip in
    property int _lastCell: -1

    function _cells() {
        const cells = []
        for (let i = 0; i < repeater.count; i++) {
            const cell = repeater.itemAt(i)
            if (cell)
                cells.push(cell)
        }
        return cells
    }

    function _fill() {
        const cells = _cells()
        cells.forEach((cell, i) => cell.show(i < items.length ? items[i] : null))
        _cursor = cells.length
        _lastCell = -1
    }

    function _flipOne() {
        const cells = _cells()
        const count = items.length
        if (!cells.length || count <= 1)
            return
        let cell = Math.floor(Math.random() * cells.length)
        if (cells.length > 1 && cell === _lastCell)
            cell = (cell + 1 + Math.floor(Math.random() * (cells.length - 1))) % cells.length
        _lastCell = cell
        const showing = cells.map(c => c.item ? c.item.path : "")
        for (let tries = 0; tries < count; tries++) {
            const candidate = items[_cursor % count]
            _cursor++
            if (showing.indexOf(candidate.path) < 0) {
                cells[cell].flipTo(candidate)
                return
            }
        }
    }

    onItemsChanged: Qt.callLater(_fill)
    onLayoutChanged: Qt.callLater(_fill)
    onIndexChanged: _flipOne()

    HoverHandler { id: hover }

    Item {
        id: content
        anchors.fill: parent
        // rounded outer corners need the GPU; the software renderer draws them square
        layer.enabled: mosaic.radius > 0 && GraphicsInfo.api !== GraphicsInfo.Software
        layer.smooth: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: mask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }

        Repeater {
            id: repeater
            model: mosaic.layout.cells.length
            delegate: Cell {
                required property int index
                readonly property var spec: mosaic.layout.cells[index]
                readonly property real colWidth: (mosaic.width - (mosaic.layout.cols - 1) * mosaic.gap) / mosaic.layout.cols
                readonly property real rowHeight: (mosaic.height - (mosaic.layout.rows - 1) * mosaic.gap) / mosaic.layout.rows
                hero: index === 0
                x: spec[0] * (colWidth + mosaic.gap)
                y: spec[1] * (rowHeight + mosaic.gap)
                width: spec[2] * colWidth + (spec[2] - 1) * mosaic.gap
                height: spec[3] * rowHeight + (spec[3] - 1) * mosaic.gap
            }
            onItemAdded: Qt.callLater(mosaic._fill)
        }
    }

    Item {
        id: mask
        anchors.fill: parent
        layer.enabled: true
        visible: false
        Rectangle {
            anchors.fill: parent
            radius: mosaic.radius
            color: "black"
        }
    }

    Item {   // ‹ › on hover: each press flips one more cell
        anchors.fill: parent
        opacity: mosaic.interactive && mosaic.hovered && mosaic.items.length > 1 ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        NavButton {
            anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
            pointsLeft: true
            onClicked: mosaic.previous()
        }
        NavButton {
            anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
            onClicked: mosaic.next()
        }
    }

    component Cell: Item {
        id: cell
        property bool hero: false
        property var item: null        // the picture showing
        property var incoming: null    // the picture loading, flipped in once it's ready
        property bool frontIsA: true

        function show(newItem) {
            flip.stop()
            turn.angle = 0
            incoming = null
            item = newItem
            frontIsA = true
            a.source = newItem ? mosaic.fileUrl(newItem.image) : ""
            b.source = ""
        }

        function flipTo(newItem) {
            if (flip.running)
                return
            incoming = newItem
            const back = frontIsA ? b : a
            back.source = mosaic.fileUrl(newItem.image)
            if (back.status === Image.Ready || back.status === Image.Error)
                flip.start()
        }

        function _loaded(image) {
            if (incoming && image === (frontIsA ? b : a) && !flip.running)
                flip.start()
        }

        Rectangle {   // seen behind the picture while it is edge-on
            anchors.fill: parent
            color: "#1c1c1e"
        }

        Item {
            id: card
            anchors.fill: parent
            transform: Rotation {
                id: turn
                origin.x: card.width / 2
                origin.y: card.height / 2
                axis { x: 1; y: 0; z: 0 }
                angle: 0
            }

            Image {
                id: a
                anchors.fill: parent
                visible: cell.frontIsA
                asynchronous: true
                cache: false
                smooth: true
                mipmap: true
                fillMode: Image.PreserveAspectCrop
                onStatusChanged: if (status === Image.Ready || status === Image.Error) cell._loaded(a)
            }
            Image {
                id: b
                anchors.fill: parent
                visible: !cell.frontIsA
                asynchronous: true
                cache: false
                smooth: true
                mipmap: true
                fillMode: Image.PreserveAspectCrop
                onStatusChanged: if (status === Image.Ready || status === Image.Error) cell._loaded(b)
            }

            Rectangle {   // caption scrim, big picture only
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: Math.min(parent.height * 0.5, caption.implicitHeight + mosaic.radius * 3)
                visible: caption.visible
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: "#a6000000" }
                }
            }
            Column {
                id: caption
                anchors {
                    left: parent.left; right: parent.right; bottom: parent.bottom
                    leftMargin: Math.max(12, mosaic.radius * 0.7); rightMargin: anchors.leftMargin
                    bottomMargin: Math.max(10, mosaic.radius * 0.6)
                }
                spacing: 2
                visible: cell.hero && mosaic.showCaption && cell.item !== null
                Text {
                    width: parent.width
                    text: cell.item ? cell.item.title : ""
                    color: "white"
                    font.pixelSize: mosaic.fontPixelSize * 1.3
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: cell.item ? cell.item.subtitle : ""
                    color: "#e6ffffff"
                    font.pixelSize: mosaic.fontPixelSize * 0.9
                    elide: Text.ElideRight
                    visible: text.length > 0
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: mosaic.interactive
            cursorShape: cell.item ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: if (cell.item) mosaic.activated(cell.item)
            property real wheel: 0
            onWheel: event => {
                wheel += event.angleDelta.y || event.angleDelta.x
                if (Math.abs(wheel) >= 120) {
                    wheel > 0 ? mosaic.previous() : mosaic.next()
                    wheel = 0
                }
            }
        }

        // the top edge tips away, the new picture swings down into place
        SequentialAnimation {
            id: flip
            NumberAnimation {
                target: turn
                property: "angle"
                from: 0
                to: 90
                duration: 260
                easing.type: Easing.InCubic
            }
            ScriptAction {
                script: {
                    cell.frontIsA = !cell.frontIsA
                    cell.item = cell.incoming
                    cell.incoming = null
                }
            }
            NumberAnimation {
                target: turn
                property: "angle"
                from: -90
                to: 0
                duration: 420
                easing.type: Easing.OutBack
                easing.overshoot: 1.2
            }
        }
    }
}
