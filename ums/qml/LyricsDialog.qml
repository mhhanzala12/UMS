import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root

    property string songTitle: ""
    property string artistName: ""
    property var lyrics: []
    property string message: ""
    property bool synchronized: false
    property real positionMs: 0
    property real durationMs: 0
    property bool playing: false
    property color accentColor: "#c8f24f"
    property color mutedColor: "#858d7b"
    property int activeIndex: -1

    signal seekRequested(int position)
    signal toggleRequested()
    signal previousRequested()
    signal nextRequested()

    function formatTime(milliseconds) {
        var totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
        var minutes = Math.floor(totalSeconds / 60)
        var seconds = totalSeconds % 60
        return minutes + ":" + (seconds < 10 ? "0" : "") + seconds
    }

    function updateActiveLine() {
        if (!synchronized || !lyrics || lyrics.length === 0) {
            activeIndex = -1
            return
        }
        var found = -1
        for (var i = 0; i < lyrics.length; ++i) {
            if (Number(lyrics[i].time_ms) <= positionMs)
                found = i
            else
                break
        }
        activeIndex = found
    }

    onPositionMsChanged: updateActiveLine()
    onLyricsChanged: updateActiveLine()
    onSynchronizedChanged: updateActiveLine()
    onOpened: {
        updateActiveLine()
        if (activeIndex >= 0)
            Qt.callLater(function() { lyricList.positionViewAtIndex(activeIndex, ListView.Center) })
    }
    onActiveIndexChanged: {
        if (visible && activeIndex >= 0)
            Qt.callLater(function() { lyricList.positionViewAtIndex(activeIndex, ListView.Center) })
    }

    modal: true
    parent: Overlay.overlay
    x: 0
    y: 0
    width: parent ? parent.width : 1440
    height: parent ? parent.height : 900
    padding: 0
    margins: 0
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: "#090c09"
        opacity: 0.985
    }

    contentItem: ColumnLayout {
        spacing: 0

        // Minimal top bar: close/back action, track identity, and a compact lyrics mark.
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 66

            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                width: 30
                height: 30
                radius: 15
                color: "#171b16"
                border.color: "#292f26"

                Text {
                    anchors.centerIn: parent
                    text: "⌄"
                    color: "#b5bdab"
                    font.pixelSize: 18
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 120, 620)
                spacing: 2
                Text {
                    width: parent.width
                    text: root.songTitle || "Now playing"
                    color: "#f0f2ed"
                    font.family: "Inter"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: root.artistName
                    color: "#77816e"
                    font.family: "Inter"
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                anchors.right: parent.right
                anchors.rightMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                width: 30
                height: 30
                radius: 15
                color: "#1a2111"
                border.color: "#303d19"

                Text {
                    anchors.centerIn: parent
                    text: "♫"
                    color: root.accentColor
                    font.pixelSize: 14
                }
            }
        }

        // Active lyric stays near the visual center as the track advances.
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 22
            Layout.rightMargin: 22

            Column {
                anchors.centerIn: parent
                width: parent.width
                spacing: 8
                visible: root.lyrics.length === 0
                Text {
                    width: parent.width
                    text: root.message || "No lyrics are available for this track."
                    color: "#929b89"
                    font.pixelSize: 15
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: !root.synchronized && root.lyrics.length > 0
                    text: "These lyrics are not timestamped, so line seeking is unavailable."
                    color: "#66705e"
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            ListView {
                id: lyricList
                anchors.fill: parent
                clip: true
                model: root.lyrics
                currentIndex: root.activeIndex
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: false
                highlightFollowsCurrentItem: true
                highlightMoveDuration: 260
                highlightRangeMode: ListView.StrictlyEnforceRange
                preferredHighlightBegin: height * 0.42
                preferredHighlightEnd: height * 0.58

                Behavior on contentY {
                    NumberAnimation {
                        duration: 280
                        easing.type: Easing.OutCubic
                    }
                }

                delegate: Item {
                    id: lyricDelegate
                    required property var modelData
                    required property int index
                    width: lyricList.width
                    height: Math.max(44, lyricText.implicitHeight + 12)

                    property bool activeLine: index === root.activeIndex
                    property bool canSeek: root.synchronized && Number(modelData.time_ms) >= 0

                    Rectangle {
                        width: Math.min(parent.width - 8, lyricText.width + 28)
                        height: parent.height
                        anchors.centerIn: parent
                        radius: 12
                        color: lyricMouse.containsMouse ? "#191d18" : "transparent"
                        opacity: lyricMouse.containsMouse ? 1 : 0.9
                    }

                    Text {
                        id: lyricText
                        width: Math.max(80, Math.min(parent.width - 48, 760))
                        anchors.centerIn: parent
                        text: modelData.text || ""
                        font.family: "Inter"
                        color: lyricDelegate.activeLine ? root.accentColor : "#899282"
                        opacity: lyricDelegate.activeLine ? 1 : 0.66
                        font.pixelSize: lyricDelegate.activeLine ? 20 : 15
                        font.weight: lyricDelegate.activeLine ? Font.Bold : Font.Medium
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        Behavior on opacity { NumberAnimation { duration: 180 } }
                        Behavior on color { ColorAnimation { duration: 180 } }
                        Behavior on font.pixelSize { NumberAnimation { duration: 180 } }
                    }

                    MouseArea {
                        id: lyricMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: lyricDelegate.canSeek ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (lyricDelegate.canSeek)
                                root.seekRequested(Number(modelData.time_ms))
                        }
                    }
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                    width: 5
                    background: Rectangle { color: "transparent" }
                    contentItem: Rectangle {
                        radius: 3
                        color: "#3b4435"
                        opacity: 0.75
                    }
                }
            }
        }

        // One shared player transport; all actions target AppBridge's existing player.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 106
            color: "#0b0e0b"
            border.color: "#141a12"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 24
                anchors.topMargin: 9
                anchors.bottomMargin: 8
                spacing: 2

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Math.min(parent.width, 500)
                    spacing: 10
                    Text {
                        text: root.formatTime(root.positionMs)
                        color: "#7d8873"
                        font.pixelSize: 9
                        font.family: "Inter"
                    }
                    Slider {
                        id: seekSlider
                        Layout.fillWidth: true
                        from: 0
                        to: Math.max(1, root.durationMs)
                        value: Math.min(root.positionMs, to)
                        onMoved: root.seekRequested(Math.round(value))
                        background: Rectangle {
                            x: seekSlider.leftPadding
                            y: seekSlider.topPadding + seekSlider.availableHeight / 2 - height / 2
                            width: seekSlider.availableWidth
                            height: 4
                            radius: 2
                            color: "#30362d"
                            Rectangle {
                                width: parent.width * seekSlider.visualPosition
                                height: parent.height
                                radius: 2
                                color: root.accentColor
                            }
                        }
                        handle: Rectangle {
                            x: seekSlider.leftPadding + seekSlider.visualPosition * (seekSlider.availableWidth - width)
                            y: seekSlider.topPadding + seekSlider.availableHeight / 2 - height / 2
                            width: 11
                            height: 11
                            radius: 6
                            color: root.accentColor
                        }
                    }
                    Text {
                        text: root.formatTime(root.durationMs)
                        color: "#7d8873"
                        font.pixelSize: 9
                    }
                }

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 20
                    Text {
                        text: "◁"
                        color: "#8a9481"
                        font.pixelSize: 17
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -8
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.previousRequested()
                        }
                    }
                    Rectangle {
                        width: 38
                        height: 38
                        radius: 19
                        color: root.accentColor
                        Text {
                            anchors.centerIn: parent
                            text: root.playing ? "Ⅱ" : "▶"
                            color: "#17200b"
                            font.pixelSize: 17
                            font.weight: Font.Bold
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.toggleRequested()
                        }
                    }
                    Text {
                        text: "▷"
                        color: "#8a9481"
                        font.pixelSize: 17
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -8
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.nextRequested()
                        }
                    }
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Math.min(parent.width - 24, 760)
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: root.synchronized ? "SYNCED LYRICS" :
                          (root.lyrics.length > 0 && root.message.length > 0
                           ? root.message : "LYRICS · TIMING UNAVAILABLE")
                    color: "#68745d"
                    font.pixelSize: 8
                    font.letterSpacing: 0.6
                }
            }
        }
    }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 170 }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 130 }
    }
}
