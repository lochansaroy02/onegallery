import QtQuick
import QtQuick.Controls
import ".."

// Help > About Gallery
Popup {
    id: dlg
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(400, parent ? parent.width - 48 : 400)
    modal: true
    focus: true
    padding: Theme.s6
    Overlay.modal: Rectangle { color: Theme.scrim }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durNormal }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.durNormal; easing.type: Theme.easing }
    }
    background: Rectangle { radius: Theme.radiusL; color: Theme.surface }

    contentItem: Column {
        spacing: Theme.s3
        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            source: Qt.resolvedUrl("../../packaging/icon.svg")
            sourceSize: Qt.size(96, 96)
            width: 96
            height: 96
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("One Gallery")
            color: Theme.text
            font.pixelSize: Theme.fontTitle + 4
            font.weight: Font.Bold
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("Version %1").arg(gallery.version)
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSmall + 1
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: qsTr("A One UI style photo gallery for KDE Plasma. Your pictures stay where they are; One Gallery only indexes the folders you choose.")
            color: Theme.text
            font.pixelSize: Theme.fontBody
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: qsTr("Place names: GeoNames (CC BY 4.0). Face models: OpenCV YuNet and SFace (Apache 2.0).")
            color: Theme.textSecondary
            font.pixelSize: Theme.fontTiny + 1
        }
        Item { width: 1; height: Theme.s1 }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Theme.s2
            PillButton { compact: true; kind: "tonal"; text: qsTr("Project page"); onClicked: Qt.openUrlExternally(gallery.projectUrl) }
            PillButton { compact: true; text: qsTr("Close"); onClicked: dlg.close() }
        }
    }
}
