import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami

KCM.SimpleKCM {
    property string cfg_source
    property alias cfg_interval: interval.value
    property alias cfg_crop: crop.checked
    property alias cfg_showCaption: caption.checked
    property alias cfg_slowZoom: zoom.checked

    readonly property var sources: ["memories", "favorites", "recent"]

    Kirigami.FormLayout {
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Show:")
            model: [i18n("Memories (this day in earlier years)"), i18n("Favorites"), i18n("Recent pictures")]
            currentIndex: Math.max(0, sources.indexOf(cfg_source))
            onActivated: cfg_source = sources[currentIndex]
        }
        QQC2.Label {
            text: i18n("On days without memories, favorites are shown, then recent pictures.")
            visible: cfg_source === "memories"
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        QQC2.SpinBox {
            id: interval
            Kirigami.FormData.label: i18n("Change picture every:")
            from: 5
            to: 3600
            stepSize: 5
            textFromValue: value => i18np("%1 second", "%1 seconds", value)
            valueFromText: text => parseInt(text) || 30
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.CheckBox {
            id: crop
            Kirigami.FormData.label: i18n("Pictures:")
            text: i18n("Fill the frame (crop the edges)")
        }
        QQC2.CheckBox {
            id: zoom
            text: i18n("Slow zoom")
            enabled: crop.checked
        }
        QQC2.CheckBox {
            id: caption
            text: i18n("Show when it was taken")
        }
    }
}
