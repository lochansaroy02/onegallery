import QtQuick
import QtQuick.Controls
import ".."

// Help > Keyboard Shortcuts
Popup {
    id: dlg
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(640, parent ? parent.width - 48 : 640)
    height: Math.min(640, parent ? parent.height - 48 : 640)
    modal: true
    focus: true
    padding: Theme.s5
    Overlay.modal: Rectangle { color: Theme.scrim }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durNormal }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.durNormal; easing.type: Theme.easing }
    }
    background: Rectangle { radius: Theme.radiusL; color: Theme.surface }

    readonly property var groups: [
        { title: qsTr("One Gallery"), keys: [
            ["Ctrl+O", qsTr("Add folder")], ["Ctrl+Shift+O", qsTr("Open picture")],
            ["Ctrl+F", qsTr("Search")], ["F5", qsTr("Rescan folders")],
            ["Ctrl+1 / 2 / 3 / 4 / 5", qsTr("Pictures / Videos / Albums / Collections / Folders")],
            ["Ctrl + / Ctrl − / Ctrl+wheel", qsTr("Bigger / smaller thumbnails")],
            ["Ctrl+Home", qsTr("Today")], ["Ctrl+,", qsTr("Settings")], ["F11", qsTr("Full screen")],
            ["Ctrl+Q", qsTr("Quit")] ] },
        { title: qsTr("Selection"), keys: [
            [qsTr("Right-click / long-press"), qsTr("Start selecting")], [qsTr("Shift+click"), qsTr("Select a range")],
            ["Ctrl+A", qsTr("Select all")], ["Ctrl+Shift+A", qsTr("Deselect all")],
            ["Ctrl+C", qsTr("Copy pictures")], ["Ctrl+Shift+C", qsTr("Copy paths")],
            ["Ctrl+L / Ctrl+R", qsTr("Rotate left / right")], ["Del", qsTr("Move to trash")],
            ["Ctrl+Shift+H", qsTr("Move to the private album")], ["Esc", qsTr("Stop selecting")] ] },
        { title: qsTr("Viewer"), keys: [
            ["← / → / Space", qsTr("Previous / next")], ["Home / End", qsTr("First / last")],
            ["+ / − / 0, wheel, double-click", qsTr("Zoom")], ["E", qsTr("Edit")], ["F", qsTr("Favorite")],
            ["I", qsTr("Details")], ["Ctrl+L / Ctrl+R", qsTr("Rotate left / right")],
            ["Del", qsTr("Move to trash")], ["Esc", qsTr("Close")],
            ["Ctrl+P", qsTr("Print")],
            ["Ctrl+Shift+B / Ctrl+Shift+L", qsTr("Set as wallpaper / lock screen")],
            [qsTr("Enter / double-click"), qsTr("Play a video with sound")], ["M", qsTr("Mute / unmute the preview")],
            ["S", qsTr("Capture the video frame")] ] },
        { title: qsTr("Video player"), keys: [
            ["Space / K", qsTr("Play / pause")], ["← / →", qsTr("Back / forward 5 seconds")],
            ["J / L", qsTr("Back / forward 10 seconds")], ["↑ / ↓, wheel", qsTr("Volume")],
            ["M", qsTr("Mute")], ["S", qsTr("Capture frame")], ["[ / ]", qsTr("Slower / faster")], ["0 … 9", qsTr("Jump to 0 … 90 %")],
            ["F, double-click", qsTr("Full screen")], ["Esc", qsTr("Close")] ] },
        { title: qsTr("Stories"), keys: [
            [qsTr("Click right / left side"), qsTr("Next / previous picture")], [qsTr("Press and hold"), qsTr("Pause")],
            ["← / →", qsTr("Previous / next")], ["Space", qsTr("Pause / play")], ["Esc", qsTr("Close")] ] },
        { title: qsTr("Editor"), keys: [
            ["Ctrl+Z / Ctrl+Shift+Z", qsTr("Undo / redo")], ["Ctrl+S", qsTr("Save")],
            ["Ctrl+Shift+S", qsTr("Save as copy")], [qsTr("Hold \\\\"), qsTr("Compare with original")],
            [qsTr("Double-click a slider"), qsTr("Reset it")], ["Esc", qsTr("Close the editor")] ] }
    ]

    contentItem: Column {
        spacing: Theme.s3
        Item {
            width: parent.width
            height: 36
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Keyboard Shortcuts")
                color: Theme.text
                font.pixelSize: Theme.fontTitle
                font.weight: Font.Bold
            }
            IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; icon: "close"; onClicked: dlg.close() }
        }
        Flickable {
            width: parent.width
            height: dlg.availableHeight - 48
            clip: true
            contentHeight: groupsColumn.height
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { }
            Column {
                id: groupsColumn
                width: parent.width
                spacing: Theme.s4
                Repeater {
                    model: dlg.groups
                    delegate: Column {
                        required property var modelData
                        width: groupsColumn.width
                        spacing: 4
                        Text {
                            text: modelData.title
                            color: Theme.accent
                            font.pixelSize: Theme.fontSmall + 1
                            font.weight: Font.DemiBold
                            bottomPadding: 2
                        }
                        Repeater {
                            model: modelData.keys
                            delegate: Item {
                                required property var modelData
                                width: groupsColumn.width
                                height: 28
                                Text {
                                    width: parent.width * 0.45
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData[0]
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSmall + 1
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Text {
                                    x: parent.width * 0.47
                                    width: parent.width * 0.53
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData[1]
                                    color: Theme.textSecondary
                                    font.pixelSize: Theme.fontSmall + 1
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
