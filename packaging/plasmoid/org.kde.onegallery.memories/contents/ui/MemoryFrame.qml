// One picture at a time, with rounded corners, a slow zoom, a caption and previous/next
// buttons on hover. Pictures change with a cross-fade, or slide up like a Windows live tile.
// Plain QtQuick (no Plasma imports), so it can also be rendered outside plasmashell
// (tools/widget_smoke.py).
import QtQuick
import QtQuick.Effects

Item {
    id: frame

    property var items: []            // [{image, path, title, subtitle}] from feed.json
    property int index: 0
    property string transition: "fade"   // "fade" or "slide"
    property bool crop: true          // fill and crop, or fit the whole picture
    property bool showCaption: true
    property bool slowZoom: true
    property bool interactive: true   // hover buttons, click, wheel (off in a panel)
    property real radius: 20
    property int interval: 30000      // ms a picture stays; the slow zoom lasts as long
    property real fontPixelSize: 13

    readonly property bool hovered: hover.hovered
    readonly property var current: items.length ? items[Math.min(index, items.length - 1)] : null

    signal activated(var item)
    signal next()
    signal previous()

    function fileUrl(path) {
        return "file://" + path.split("/").map(encodeURIComponent).join("/")
    }

    property Item _shown: null
    property Item _pending: null
    property int _lastIndex: -1

    function _load() {
        if (!current) {
            if (_pending) { _pending.destroy(); _pending = null }
            if (_shown) { _shown.destroy(); _shown = null }
            return
        }
        // backwards (slides down) only when stepping to the previous picture
        const count = items.length
        const back = _lastIndex >= 0 && count > 2 && index === (_lastIndex - 1 + count) % count
        _lastIndex = index
        const url = fileUrl(current.image)
        if (_shown && _shown.source.toString() === url && !_pending)
            return
        if (_pending)
            _pending.destroy()
        _pending = slide.createObject(slides, {
            source: url, item: current, origin: index % 4, direction: back ? -1 : 1 })
    }

    function _reveal(page) {
        if (page !== _pending)
            return
        _pending = null
        const before = _shown
        _shown = page
        page.reveal(before)
    }

    onCurrentChanged: _load()
    Component.onCompleted: _load()

    HoverHandler { id: hover }

    Item {
        id: content
        anchors.fill: parent
        // rounded corners need the GPU; the software renderer shows the pictures square
        layer.enabled: frame.radius > 0 && GraphicsInfo.api !== GraphicsInfo.Software
        layer.smooth: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: mask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }

        Rectangle {
            anchors.fill: parent
            color: frame.crop ? "#1c1c1e" : "transparent"
        }

        Item {
            id: slides
            anchors.fill: parent
            clip: true
        }
    }

    Item {
        id: mask
        anchors.fill: parent
        layer.enabled: true
        visible: false
        Rectangle {
            anchors.fill: parent
            radius: frame.radius
            color: "black"
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: frame.interactive
        cursorShape: frame.current ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (frame.current) frame.activated(frame.current)
        property real wheel: 0
        onWheel: event => {
            wheel += event.angleDelta.y || event.angleDelta.x
            if (Math.abs(wheel) >= 120) {
                wheel > 0 ? frame.previous() : frame.next()
                wheel = 0
            }
        }
    }

    // ---- hover controls ------------------------------------------------------------------
    Item {
        anchors.fill: parent
        opacity: frame.interactive && frame.hovered && frame.items.length > 1 ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

        NavButton {
            anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
            pointsLeft: true
            onClicked: frame.previous()
        }
        NavButton {
            anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
            onClicked: frame.next()
        }
        Rectangle {   // "3 / 24"
            anchors { right: parent.right; top: parent.top; margins: Math.max(10, frame.radius * 0.6) }
            width: counter.implicitWidth + 16
            height: counter.implicitHeight + 8
            radius: height / 2
            color: "#73000000"
            Text {
                id: counter
                anchors.centerIn: parent
                text: (Math.min(frame.index, frame.items.length - 1) + 1) + " / " + frame.items.length
                color: "white"
                font.pixelSize: frame.fontPixelSize * 0.85
            }
        }
    }

    // one picture with its caption; the caption fades or slides along with it
    Component {
        id: slide
        Item {
            id: page
            property var item
            property alias source: img.source
            property int origin: 0
            property int direction: 1      // 1: the new picture comes up from below
            property Item before: null
            width: slides.width
            height: slides.height
            opacity: 0
            clip: true   // the slow zoom stays inside the picture while sliding

            Image {
                id: img
                anchors.fill: parent
                asynchronous: true
                cache: false
                smooth: true
                mipmap: true
                fillMode: frame.crop ? Image.PreserveAspectCrop : Image.PreserveAspectFit
                transformOrigin: [Item.TopLeft, Item.BottomRight, Item.TopRight, Item.BottomLeft][page.origin]
                onStatusChanged: if (status === Image.Ready || status === Image.Error) frame._reveal(page)
            }

            Rectangle {   // caption scrim
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: Math.min(parent.height * 0.55, caption.implicitHeight + frame.radius * 3)
                visible: frame.showCaption
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: "#a6000000" }
                }
            }

            Column {
                id: caption
                anchors {
                    left: parent.left; right: parent.right; bottom: parent.bottom
                    leftMargin: Math.max(14, frame.radius * 0.8); rightMargin: anchors.leftMargin
                    bottomMargin: Math.max(12, frame.radius * 0.7)
                }
                spacing: 2
                visible: frame.showCaption
                Text {
                    width: parent.width
                    text: page.item ? page.item.title : ""
                    color: "white"
                    font.pixelSize: frame.fontPixelSize * 1.45
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: page.item ? page.item.subtitle : ""
                    color: "#e6ffffff"
                    font.pixelSize: frame.fontPixelSize
                    elide: Text.ElideRight
                    visible: text.length > 0
                }
            }

            function reveal(previous) {
                if (previous)
                    previous.settle()   // still arriving: finish it now (fast clicking)
                before = previous
                if (frame.transition === "slide" && previous) {
                    opacity = 1
                    slideIn.from = direction * height
                    slideOut.target = previous
                    slideOut.to = -direction * height
                    sliding.start()
                } else {
                    fade.start()
                }
                if (frame.slowZoom && frame.crop)
                    zoom.start()
            }

            function settle() {
                fade.stop()
                sliding.stop()
                y = 0
                opacity = 1
                _dropBefore()
            }

            function _dropBefore() {
                if (before) { before.destroy(); before = null }
            }

            OpacityAnimator {
                id: fade
                target: page
                from: 0
                to: 1
                duration: 800
                easing.type: Easing.InOutQuad
                onFinished: page._dropBefore()
            }
            // Windows live tile: the new picture pushes the old one out, fast then settling
            ParallelAnimation {
                id: sliding
                onFinished: page._dropBefore()
                NumberAnimation {
                    id: slideIn
                    target: page
                    property: "y"
                    to: 0
                    duration: 900
                    easing.type: Easing.OutQuint
                }
                NumberAnimation {
                    id: slideOut
                    property: "y"
                    from: 0
                    duration: 900
                    easing.type: Easing.OutQuint
                }
            }
            NumberAnimation {
                id: zoom
                target: img
                property: "scale"
                from: 1.0
                to: 1.07
                duration: frame.interval + 2000
                easing.type: Easing.InOutSine
            }
        }
    }
}
