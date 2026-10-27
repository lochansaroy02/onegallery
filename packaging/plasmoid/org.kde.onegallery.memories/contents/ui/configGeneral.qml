import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami

KCM.SimpleKCM {
    id: page

    property string cfg_source
    property var cfg_folders: []
    property string cfg_transition
    property alias cfg_interval: interval.value
    property alias cfg_crop: crop.checked
    property alias cfg_showCaption: caption.checked
    property alias cfg_slowZoom: zoom.checked

    readonly property var sources: ["memories", "favorites", "recent", "folder"]
    readonly property var transitions: ["fade", "slide", "mosaic"]

    function localPath(url) {
        return decodeURIComponent(url.toString().replace(/^file:\/\//, ""))
    }

    FolderDialog {
        id: folderDialog
        title: i18n("Choose a Folder of Pictures")
        onAccepted: {
            const path = page.localPath(selectedFolder)
            if (path && page.cfg_folders.indexOf(path) < 0)
                page.cfg_folders = page.cfg_folders.concat([path])
        }
    }

    Kirigami.FormLayout {
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Show:")
            model: [i18n("Memories (this day in earlier years)"), i18n("Favorites"),
                    i18n("Recent pictures"), i18n("Pictures from folders")]
            currentIndex: Math.max(0, sources.indexOf(cfg_source))
            onActivated: cfg_source = sources[currentIndex]
        }
        QQC2.Label {
            text: i18n("On days without memories, favorites are shown, then recent pictures.")
            visible: cfg_source === "memories"
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        ColumnLayout {
            Kirigami.FormData.label: i18n("Folders:")
            visible: cfg_source === "folder"
            spacing: Kirigami.Units.smallSpacing

            Repeater {
                model: cfg_folders
                delegate: RowLayout {
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    Kirigami.Icon {
                        source: "folder-pictures"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }
                    QQC2.Label {
                        text: modelData
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                        Layout.maximumWidth: Kirigami.Units.gridUnit * 18
                    }
                    QQC2.ToolButton {
                        icon.name: "list-remove"
                        text: i18n("Remove")
                        display: QQC2.AbstractButton.IconOnly
                        QQC2.ToolTip.text: text
                        QQC2.ToolTip.visible: hovered
                        onClicked: page.cfg_folders = page.cfg_folders.filter((_, i) => i !== index)
                    }
                }
            }
            QQC2.Button {
                icon.name: "folder-add"
                text: i18n("Add Folder…")
                onClicked: folderDialog.open()
            }
            QQC2.Label {
                text: i18n("Any folder, also on other drives, whether or not it is in One Gallery. Sub-folders are included, and a new selection of up to 60 pictures per folder is made every day.")
                wrapMode: Text.Wrap
                Layout.maximumWidth: Kirigami.Units.gridUnit * 20
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.ComboBox {
            id: transition
            Kirigami.FormData.label: i18n("Animation:")
            model: [i18n("Cross-fade"), i18n("Live tile: slide up"), i18n("Live tile: flip mosaic")]
            currentIndex: Math.max(0, transitions.indexOf(cfg_transition))
            onActivated: cfg_transition = transitions[currentIndex]
        }
        QQC2.Label {
            text: i18n("Like the Windows Photos live tile: a mosaic of pictures, one tile flipping at a time.")
            visible: cfg_transition === "mosaic"
            wrapMode: Text.Wrap
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        QQC2.SpinBox {
            id: interval
            Kirigami.FormData.label: cfg_transition === "mosaic" ? i18n("Flip a tile every:")
                                                                : i18n("Change picture every:")
            from: 3
            to: 3600
            textFromValue: value => i18np("%1 second", "%1 seconds", value)
            valueFromText: text => parseInt(text) || 30
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.CheckBox {
            id: crop
            Kirigami.FormData.label: i18n("Pictures:")
            text: i18n("Fill the frame (crop the edges)")
            enabled: cfg_transition !== "mosaic"   // mosaic tiles are always filled
        }
        QQC2.CheckBox {
            id: zoom
            text: i18n("Slow zoom")
            enabled: crop.checked && cfg_transition !== "mosaic"
        }
        QQC2.CheckBox {
            id: caption
            text: i18n("Show when it was taken")
        }
    }
}
