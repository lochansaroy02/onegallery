// Round ‹ / › button shown over the pictures on hover.
import QtQuick
import QtQuick.Shapes

Rectangle {
    id: button
    property bool pointsLeft: false
    signal clicked()

    width: 34
    height: 34
    radius: 17
    color: area.pressed ? "#a6000000" : area.containsMouse ? "#8c000000" : "#66000000"
    Behavior on color { ColorAnimation { duration: 120 } }

    Shape {
        anchors.centerIn: parent
        width: 8
        height: 14
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "white"
            strokeWidth: 2
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            startX: button.pointsLeft ? 7 : 1; startY: 1
            PathLine { x: button.pointsLeft ? 1 : 7; y: 7 }
            PathLine { x: button.pointsLeft ? 7 : 1; y: 13 }
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
