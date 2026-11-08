import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root

    property string songTitle: ""
    property string artistName: ""
    property var lyrics: []
    property string message: ""
    property string source: ""
    property string coverArt: ""
    property bool lyricsSynchronized: false
    property real positionMs: 0
    property real durationMs: 0
    property bool playing: false
    property color accentColor: "#c8f24f"
    property color mutedColor: "#858d7b"
    property int activeIndex: -1

    signal seekRequested(int position)
    signal timingUnavailableClicked()
    signal toggleRequested()
    signal previousRequested()
    signal nextRequested()

    function formatTime(milliseconds) {
        var totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
        var minutes = Math.floor(totalSeconds / 60)
        var seconds = totalSeconds % 60
        return minutes + ":" + (seconds < 10 ? "0" : "") + seconds
    }

    function activateLyricLine(index) {
        if (!lyricsSynchronized || !lyrics || index < 0 || index >= lyrics.length)
            return false
        var row = lyrics[index]
        var timestamp = Number(row.time_ms)
        if (!isFinite(timestamp) || timestamp < 0)
            return false
        // Activate the clicked row immediately; the player position signal
        // then keeps it locked to the actual playback position.
        activeIndex = index
        if (visible && index < lyricList.count)
            lyricList.positionViewAtIndex(index, ListView.Center)
        return true
    }

    function updateActiveLine() {
        if (!lyricsSynchronized || !lyrics || lyrics.length === 0) {
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
    onLyricsSynchronizedChanged: updateActiveLine()
    onOpened: {
        updateActiveLine()
        if (activeIndex >= 0 && activeIndex < lyricList.count)
            Qt.callLater(function() {
                if (activeIndex >= 0 && activeIndex < lyricList.count)
                    lyricList.positionViewAtIndex(activeIndex, ListView.Center)
            })
    }
    onActiveIndexChanged: {
        if (visible && activeIndex >= 0 && activeIndex < lyricList.count)
            Qt.callLater(function() {
                if (activeIndex >= 0 && activeIndex < lyricList.count)
                    lyricList.positionViewAtIndex(activeIndex, ListView.Center)
            })
    }

    modal: true
    parent: Overlay.overlay
    x: 0
    y: 0
    width: parent ? parent.width : 1440
    height: parent ? parent.height : 900
    padding: 0
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: "#080b08"
        opacity: 0.985
    }

    contentItem: ColumnLayout {
        spacing: 0

        // Minimal top bar: close/back action, track identity, and a compact lyrics mark.
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 72

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
                    font.family: "Segoe UI"
                    font.pixelSize: 14
                    font.weight: Font.Bold
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: root.artistName
                    color: "#77816e"
                    font.family: "Segoe UI"
                    font.pixelSize: 11
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
                    visible: !root.lyricsSynchronized && root.lyrics.length > 0
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
                spacing: 3
                boundsBehavior: Flickable.StopAtBounds
                highlightFollowsCurrentItem: true
                highlightMoveDuration: 320
                highlightRangeMode: ListView.ApplyRange
                preferredHighlightBegin: height * 0.42
                preferredHighlightEnd: height * 0.58

                Behavior on contentY {
                    NumberAnimation {
                        duration: 320
                        easing.type: Easing.OutCubic
                    }
                }

                delegate: Item {
                    id: lyricDelegate
                    property var lyric: modelData
                    property int rowIndex: index
                    width: lyricList.width
                    height: Math.max(42, lyricText.implicitHeight + 10)

                    property bool activeLine: root.lyricsSynchronized && rowIndex === root.activeIndex
                    property bool previousLine: root.lyricsSynchronized && root.activeIndex >= 0
                                                 && rowIndex < root.activeIndex
                    property bool upcomingLine: root.lyricsSynchronized
                                                 && (root.activeIndex < 0 || rowIndex > root.activeIndex)
                    property bool canSeek: root.lyricsSynchronized
                                                    && lyric.time_ms !== undefined
                                                    && isFinite(Number(lyric.time_ms))
                                                    && Number(lyric.time_ms) >= 0

                    Rectangle {
                        width: Math.min(parent.width - 8, lyricText.width + 28)
                        height: parent.height
                        anchors.centerIn: parent
                        radius: 12
                        color: lyricMouse.containsMouse ? "#1b2118" : "transparent"
                        border.width: lyricDelegate.activeLine ? 1 : 0
                        border.color: "#303d20"
                        opacity: lyricMouse.containsMouse ? 1 : 0.9
                        Behavior on color { ColorAnimation { duration: 150 } }
                    }

                    Text {
                        id: lyricText
                        width: Math.max(80, Math.min(parent.width - 48, 880))
                        anchors.centerIn: parent
                        text: lyricDelegate.lyric.text || ""
                        font.family: "Segoe UI"
                        color: lyricDelegate.activeLine ? "#caff4b"
                             : (lyricMouse.containsMouse ? "#c0cbb4"
                                : (lyricDelegate.previousLine ? "#626c59" : "#929b8a"))
                        opacity: lyricDelegate.activeLine ? 1
                               : (lyricMouse.containsMouse ? 0.98
                                  : (lyricDelegate.previousLine ? 0.42 : 0.82))
                        font.pixelSize: lyricDelegate.activeLine ? 22
                                      : (lyricDelegate.previousLine ? 15 : 16)
                        font.weight: lyricDelegate.activeLine ? Font.Bold
                                     : (lyricDelegate.previousLine ? Font.Normal : Font.DemiBold)
                        font.letterSpacing: lyricDelegate.activeLine ? 0.05 : 0.0
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
                        Behavior on font.pixelSize { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                    }

                    MouseArea {
                        id: lyricMouse
                        anchors.fill: parent
                        z: 10
                        acceptedButtons: Qt.LeftButton
                        hoverEnabled: true
                        preventStealing: true
                        cursorShape: lyricDelegate.canSeek ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (lyricDelegate.canSeek) {
                                root.activateLyricLine(lyricDelegate.rowIndex)
                                root.seekRequested(Math.max(0, Number(lyricDelegate.lyric.time_ms)))
                            } else {
                                root.timingUnavailableClicked()
                            }
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

        // Minimal now-playing footer: spinning artwork and a seekable,
        // playback-reactive waveform replace the large transport controls.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 86
            color: "#090c09"
            border.color: "#141a12"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 22
                anchors.rightMargin: 22
                anchors.topMargin: 9
                anchors.bottomMargin: 9
                spacing: 14

                Item {
                    id: coverDisc
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 58

                    // Rotate the complete record, not a square image clipped by
                    // a rounded rectangle. The circular label and spindle hole
                    // make the artwork read like a small vinyl record.
                    NumberAnimation on rotation {
                        from: 0
                        to: 360
                        duration: 9000
                        loops: Animation.Infinite
                        running: root.playing
                        easing.type: Easing.Linear
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: width / 2
                        color: "#10130f"
                        border.color: "#424b38"
                        border.width: 1
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 51
                        height: 51
                        radius: width / 2
                        color: "transparent"
                        border.color: "#293126"
                        border.width: 1
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 45
                        height: 45
                        radius: width / 2
                        color: "transparent"
                        border.color: "#20271e"
                        border.width: 1
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 39
                        height: 39
                        radius: width / 2
                        color: "transparent"
                        border.color: "#30382b"
                        border.width: 1
                    }

                    Rectangle {
                        id: discLabel
                        anchors.centerIn: parent
                        width: 31
                        height: 31
                        radius: width / 2
                        color: "#252d1f"
                        border.color: "#657250"
                        border.width: 1
                        clip: true

                        Image {
                            id: coverImage
                            anchors.fill: parent
                            source: root.coverArt
                            visible: status === Image.Ready
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            cache: true
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: coverImage.status !== Image.Ready
                            text: "♫"
                            color: root.accentColor
                            font.pixelSize: 15
                            font.weight: Font.Bold
                        }
                    }

                    // Small spindle hole in the center of the record label.
                    Rectangle {
                        anchors.centerIn: parent
                        width: 5
                        height: 5
                        radius: width / 2
                        color: "#090b08"
                        border.color: "#b0b99e"
                        border.width: 0.7
                        z: 2
                    }
                }

                ColumnLayout {
                    Layout.preferredWidth: 148
                    Layout.maximumWidth: 180
                    Layout.minimumWidth: 112
                    spacing: 3
                    Text {
                        Layout.fillWidth: true
                        text: root.playing ? "NOW PLAYING" : "PAUSED"
                        color: root.accentColor
                        font.family: "Segoe UI"
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 0.8
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.formatTime(root.positionMs) + "  /  " + root.formatTime(root.durationMs)
                        color: "#a0a991"
                        font.family: "Segoe UI"
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.source.length ? root.source.toUpperCase() : "LYRICS"
                        color: "#68745d"
                        font.family: "Segoe UI"
                        font.pixelSize: 8
                        font.letterSpacing: 0.5
                        elide: Text.ElideRight
                    }
                }

                Item {
                    id: waveformArea
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 100
                    Row {
                        id: waveformBars
                        anchors.fill: parent
                        spacing: 3
                        Repeater {
                            model: 44
                            delegate: Rectangle {
                                property real baseHeight: 5 + ((index * 11 + 7) % 15)
                                width: Math.max(2, (waveformBars.width - 43 * waveformBars.spacing) / 44)
                                height: root.playing
                                        ? baseHeight + Math.abs(Math.sin(root.positionMs / 175 + index * 0.78)) * 13
                                        : Math.max(3, baseHeight * 0.34)
                                anchors.verticalCenter: parent.verticalCenter
                                radius: 2
                                color: root.durationMs > 0 && index / 44 <= root.positionMs / root.durationMs
                                       ? root.accentColor : "#353d30"
                                Behavior on height {
                                    NumberAnimation { duration: 130; easing.type: Easing.OutCubic }
                                }
                                Behavior on color { ColorAnimation { duration: 180 } }
                            }
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        z: 2
                        cursorShape: root.durationMs > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (root.durationMs > 0)
                                root.seekRequested(Math.round(root.durationMs * Math.max(0, Math.min(1, mouse.x / width))))
                        }
                    }
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
