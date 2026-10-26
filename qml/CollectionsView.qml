import QtQuick
import QtQuick.Controls
import "."
import "components"

// Collections tab: Stories (memories), People and Places.
Item {
    id: view
    property real bottomInset: 0
    signal playStory(var story)
    signal openPeople()
    signal openPlaces()
    signal openPerson(int personId, string name)
    signal openPlace(string key, string name)

    readonly property var win: ApplicationWindow.window
    readonly property real headerHeight: Math.max(150, Math.min(250, height * 0.3))
    readonly property real collapse: Math.max(0, Math.min(1, flick.contentY / (headerHeight * 0.7)))

    function summary() {
        var parts = []
        if (collections.stories.length)
            parts.push(collections.stories.length === 1 ? qsTr("1 story") : qsTr("%1 stories").arg(collections.stories.length))
        if (collections.people.length)
            parts.push(collections.people.length === 1 ? qsTr("1 person") : qsTr("%1 people").arg(collections.people.length))
        if (collections.places.length)
            parts.push(collections.places.length === 1 ? qsTr("1 place") : qsTr("%1 places").arg(collections.places.length))
        return parts.length ? parts.join(" · ") : qsTr("Stories, people and places from your pictures")
    }

    // ---- building blocks ------------------------------------------------------------------------
    component SectionTitle: Item {
        property string title
        property bool showAll: false
        signal seeAll()
        width: parent ? parent.width : 0
        height: 52
        Text {
            x: Theme.pageMargin + 4
            anchors.verticalCenter: parent.verticalCenter
            text: parent.title
            color: Theme.text
            font.pixelSize: Theme.fontTitle
            font.weight: Font.Bold
        }
        PillButton {
            visible: parent.showAll
            anchors.right: parent.right
            anchors.rightMargin: Theme.pageMargin - 4
            anchors.verticalCenter: parent.verticalCenter
            compact: true
            kind: "text"
            text: qsTr("See all")
            onClicked: parent.seeAll()
        }
    }

    component InfoCard: Rectangle {
        id: card
        property string icon: "collections"
        property string title
        property string text
        property string action: ""
        property real progress: -1          // 0..1 shows a progress bar
        signal triggered()
        x: Theme.pageMargin
        width: (parent ? parent.width : 0) - 2 * Theme.pageMargin
        height: infoCol.implicitHeight + Theme.s5 * 2
        radius: Theme.radiusL
        color: Theme.surface
        Rectangle {
            id: badge
            x: Theme.s5
            y: Theme.s5
            width: 48
            height: 48
            radius: 24
            color: Theme.accentSoft
            Icon { anchors.centerIn: parent; name: card.icon; color: Theme.accent; size: 22 }
        }
        Column {
            id: infoCol
            anchors.left: badge.right
            anchors.leftMargin: Theme.s4
            anchors.right: parent.right
            anchors.rightMargin: Theme.s5
            y: Theme.s5
            spacing: Theme.s2
            Text {
                width: parent.width
                text: card.title
                wrapMode: Text.Wrap
                color: Theme.text
                font.pixelSize: Theme.fontBody + 1
                font.weight: Font.DemiBold
            }
            Text {
                width: parent.width
                visible: card.text !== ""
                text: card.text
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall + 1
            }
            Rectangle {
                visible: card.progress >= 0
                width: parent.width
                height: 6
                radius: 3
                color: Theme.surfaceHigh
                Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, card.progress))
                    height: parent.height
                    radius: 3
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: 200 } }
                }
            }
            PillButton {
                visible: card.action !== ""
                compact: true
                text: card.action
                onClicked: card.triggered()
            }
        }
    }

    CollapsingHeader {
        id: bar
        z: 2
        width: parent.width
        title: qsTr("Collections")
        progress: view.collapse
        IconButton { id: menuButton; icon: "more"; tip: qsTr("Menu"); onClicked: view.win.openAppMenu(menuButton) }
    }

    Flickable {
        id: flick
        anchors.top: bar.bottom
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        contentHeight: col.height + view.bottomInset + Theme.s6

        Column {
            id: col
            width: flick.width
            spacing: Theme.s2

            BigTitle {
                width: parent.width
                height: view.headerHeight
                title: qsTr("Collections")
                subtitle: view.summary()
                progress: view.collapse
            }

            // ---- Stories ---------------------------------------------------------------------
            SectionTitle { title: qsTr("Stories") }
            ListView {
                id: storyList
                visible: collections.stories.length > 0
                width: parent.width
                height: 300
                orientation: ListView.Horizontal
                leftMargin: Theme.pageMargin
                rightMargin: Theme.pageMargin
                spacing: Theme.s3
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: collections.stories
                delegate: Item {
                    required property var modelData
                    width: 212
                    height: 296
                    scale: storyMouse.pressed ? 0.97 : 1
                    Behavior on scale { NumberAnimation { duration: Theme.durFast } }
                    RoundedImage {
                        anchors.fill: parent
                        radius: Theme.radiusL
                        source: modelData.cover
                    }
                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusL
                        gradient: Gradient {
                            GradientStop { position: 0.45; color: "transparent" }
                            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.7) }
                        }
                    }
                    Rectangle {
                        x: Theme.s3
                        y: Theme.s3
                        width: playRow.implicitWidth + 20
                        height: 28
                        radius: 14
                        color: Qt.rgba(0, 0, 0, 0.35)
                        Row {
                            id: playRow
                            anchors.centerIn: parent
                            spacing: 4
                            Icon { name: "play"; size: 13; color: "white"; filled: true; anchors.verticalCenter: parent.verticalCenter }
                            Text {
                                text: modelData.count
                                color: "white"
                                font.pixelSize: Theme.fontSmall
                                font.weight: Font.DemiBold
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: Theme.s4
                        spacing: 2
                        Text {
                            width: parent.width
                            text: modelData.title
                            color: "white"
                            font.pixelSize: Theme.fontTitle
                            font.weight: Font.Bold
                            wrapMode: Text.Wrap
                        }
                        Text {
                            width: parent.width
                            text: modelData.subtitle
                            color: "#E5E5EA"
                            font.pixelSize: Theme.fontSmall
                            elide: Text.ElideRight
                        }
                    }
                    MouseArea {
                        id: storyMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: view.playStory(modelData)
                    }
                }
            }
            InfoCard {
                visible: collections.stories.length === 0
                icon: "stories"
                title: qsTr("No memories today")
                text: qsTr("Stories show pictures you took around this date in earlier years. Check back tomorrow.")
            }

            // ---- People ----------------------------------------------------------------------
            SectionTitle {
                title: qsTr("People")
                showAll: collections.people.length > 0 || collections.hiddenPeople.length > 0
                onSeeAll: view.openPeople()
            }
            InfoCard {
                visible: collections.peopleState === "unavailable"
                icon: "users"
                title: qsTr("Face grouping isn't installed")
                text: qsTr("People needs OpenCV. Run ./update.sh in the One Gallery folder to install it, then restart One Gallery.")
            }
            InfoCard {
                visible: collections.peopleState === "off"
                icon: "users"
                title: qsTr("Find people in your pictures")
                text: qsTr("One Gallery can recognise faces and group pictures of the same person. Everything runs on this computer and nothing is uploaded. The first time, it downloads face models (38 MB).")
                action: qsTr("Turn on")
                onTriggered: collections.enablePeople()
            }
            InfoCard {
                visible: collections.peopleState === "downloading"
                icon: "users"
                title: qsTr("Downloading face models… %1%").arg(Math.round(collections.downloadProgress * 100))
                progress: collections.downloadProgress
            }
            InfoCard {
                visible: collections.peopleState === "scanning" && collections.people.length === 0
                icon: "users"
                title: qsTr("Looking for faces…")
                text: collections.facesTotal > 0
                      ? qsTr("%1 of %2 pictures").arg(collections.facesDone.toLocaleString(Qt.locale(), "f", 0))
                                                   .arg(collections.facesTotal.toLocaleString(Qt.locale(), "f", 0))
                      : ""
                progress: collections.facesTotal > 0 ? collections.facesDone / collections.facesTotal : 0
            }
            InfoCard {
                visible: collections.peopleState === "ready" && collections.people.length === 0
                icon: "users"
                title: qsTr("No people found yet")
                text: qsTr("A person appears once their face is found in at least 3 pictures.")
            }
            ListView {
                visible: collections.people.length > 0 && collections.peopleState !== "off"
                width: parent.width
                height: 150
                orientation: ListView.Horizontal
                leftMargin: Theme.pageMargin
                rightMargin: Theme.pageMargin
                spacing: Theme.s3
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: collections.people
                delegate: PersonAvatar {
                    required property var modelData
                    person: modelData
                    onClicked: view.openPerson(modelData.id, modelData.name)
                }
            }
            Text {
                visible: collections.peopleState === "scanning" && collections.people.length > 0
                x: Theme.pageMargin + 4
                text: qsTr("Still looking for faces… %1 of %2").arg(collections.facesDone).arg(collections.facesTotal)
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall
            }

            // ---- Places ----------------------------------------------------------------------
            SectionTitle {
                title: qsTr("Places")
                showAll: collections.placesState === "ready" && collections.places.length > 0
                onSeeAll: view.openPlaces()
            }
            InfoCard {
                visible: collections.placesState === "loading"
                icon: "pin"
                title: qsTr("Reading locations…")
            }
            InfoCard {
                visible: collections.placesState === "no-gps"
                icon: "pin"
                title: qsTr("No pictures with a location yet")
                text: qsTr("Pictures taken with location turned on (most phones do this) are grouped here by town.")
            }
            InfoCard {
                visible: collections.placesState === "need-data"
                icon: "pin"
                title: qsTr("Name the places in %1 pictures").arg(collections.gpsCount.toLocaleString(Qt.locale(), "f", 0))
                text: qsTr("One Gallery needs a list of towns (3 MB, from GeoNames) to turn locations into place names. Lookups then work offline.")
                action: qsTr("Download")
                onTriggered: collections.downloadPlaceNames()
            }
            InfoCard {
                visible: collections.placesState === "downloading"
                icon: "pin"
                title: qsTr("Downloading place names… %1%").arg(Math.round(collections.downloadProgress * 100))
                progress: collections.downloadProgress
            }
            ListView {
                visible: collections.placesState === "ready" && collections.places.length > 0
                width: parent.width
                height: 206
                orientation: ListView.Horizontal
                leftMargin: Theme.pageMargin
                rightMargin: Theme.pageMargin
                spacing: Theme.s3
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: collections.places
                delegate: Item {
                    required property var modelData
                    width: 156
                    height: 206
                    RoundedImage {
                        id: placeCover
                        width: 156
                        height: 156
                        radius: Theme.radiusL
                        source: modelData.cover
                        scale: placeMouse.pressed ? 0.97 : 1
                        Behavior on scale { NumberAnimation { duration: Theme.durFast } }
                    }
                    Column {
                        anchors.top: placeCover.bottom
                        anchors.topMargin: Theme.s2
                        x: 4
                        width: parent.width - 8
                        Text {
                            width: parent.width
                            text: modelData.place
                            elide: Text.ElideRight
                            color: Theme.text
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                        }
                        Text {
                            width: parent.width
                            text: modelData.place === modelData.country || modelData.country === ""
                                  ? modelData.count.toLocaleString(Qt.locale(), "f", 0)
                                  : modelData.country + " · " + modelData.count.toLocaleString(Qt.locale(), "f", 0)
                            elide: Text.ElideRight
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSmall
                        }
                    }
                    MouseArea {
                        id: placeMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: view.openPlace(modelData.key, modelData.place)
                    }
                }
            }
        }
    }
}
