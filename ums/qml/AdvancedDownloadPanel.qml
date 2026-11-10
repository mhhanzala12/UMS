import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root

    property var palette: ({})
    property var presets: ({})
    property string selectedPreset: "Best Available Quality"
    property bool expanded: false
    property bool showSourceQuality: true
    property string activeSection: "source"

    signal presetChanged(string name)
    signal savePresetRequested(string optionsJson)

    spacing: 10

    function setCombo(combo, value, fallback) {
        var text = String(value === undefined || value === null || value === "" ? fallback : value)
        var rows = combo.model
        var index = rows && rows.indexOf ? rows.indexOf(text) : -1
        combo.currentIndex = index >= 0 ? index : 0
        if (combo.editable)
            combo.editText = text
    }

    function applyPreset(name, preset) {
        var value = preset || presets[name] || {}
        if (!value || !Object.keys(value).length)
            return
        setCombo(sourceFormat, value.format, "bestvideo+bestaudio/best")
        setCombo(outputContainer, String(value.container || "original").toUpperCase() === "ORIGINAL"
                 ? "Original" : String(value.container || "mp4").toUpperCase(), "Original")
        setCombo(videoCodec, value.video_codec, "copy")
        setCombo(audioCodec, value.audio_codec, "copy")
        setCombo(videoEncoder, value.video_encoder, "Auto")
        setCombo(rateControl, value.rate_control, "Source")
        setCombo(encoderPreset, value.encoder_preset, "medium")
        setCombo(frameRate, value.fps, "Source")
        setCombo(frameMode, value.fps_mode, "CFR")
        setCombo(resolution, value.resolution, "Source")
        setCombo(sampleRate, value.sample_rate, "Source")
        setCombo(channels, value.channels, "Source")
        setCombo(pixelFormat, value.pixel_format, "Auto")
        setCombo(colorSpace, value.color_space, "Auto")
        setCombo(colorRange, value.color_range, "Auto")
        videoBitrate.text = String(value.video_bitrate || "")
        audioBitrate.text = String(value.audio_bitrate || "")
        var quality = Number(value.crf === undefined ? 23 : value.crf)
        qualityValue.value = isFinite(quality) ? Math.max(0, Math.min(63, quality)) : 23
        customScale.text = String(value.custom_scale || "")
        profileName.text = String(value.profile || "")
        codecLevel.text = String(value.level || "")
        subtitles.checked = !!value.write_subtitles
        automaticCaptions.checked = !!value.write_automatic_subtitles
        embedSubtitles.checked = !!value.embed_subtitles
        preserveMetadata.checked = value.preserve_metadata !== false
        saveThumbnail.checked = !!value.download_thumbnail
    }

    function options() {
        var container = String(outputContainer.currentText || "Original").toLowerCase()
        return {
            format: String(sourceFormat.editText || sourceFormat.currentText || "bestvideo+bestaudio/best").trim(),
            container: container === "original" ? "original" : container,
            video_codec: videoCodec.currentText,
            audio_codec: audioCodec.currentText,
            video_encoder: videoEncoder.currentText,
            profile: profileName.text.trim(),
            level: codecLevel.text.trim(),
            pixel_format: pixelFormat.currentText,
            color_space: colorSpace.currentText,
            color_range: colorRange.currentText,
            rate_control: rateControl.currentText,
            video_bitrate: videoBitrate.text.trim(),
            audio_bitrate: audioBitrate.text.trim(),
            crf: String(qualityValue.value),
            encoder_preset: encoderPreset.currentText,
            fps: String(frameRate.editText || frameRate.currentText || "Source").trim(),
            fps_mode: frameMode.currentText,
            resolution: resolution.currentText,
            custom_scale: resolution.currentText === "Custom" ? customScale.text.trim() : "",
            sample_rate: sampleRate.currentText,
            channels: channels.currentText,
            write_subtitles: subtitles.checked,
            write_automatic_subtitles: automaticCaptions.checked,
            embed_subtitles: embedSubtitles.checked,
            preserve_metadata: preserveMetadata.checked,
            download_thumbnail: saveThumbnail.checked
        }
    }

    onSelectedPresetChanged: applyPreset(selectedPreset, presets[selectedPreset])
    onPresetsChanged: applyPreset(selectedPreset, presets[selectedPreset])
    onShowSourceQualityChanged: {
        if (!showSourceQuality && activeSection === "source")
            activeSection = "encoding"
    }
    Component.onCompleted: {
        if (!showSourceQuality && activeSection === "source")
            activeSection = "encoding"
        applyPreset(selectedPreset, presets[selectedPreset])
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: profileRow.implicitHeight + 30
        radius: 13
        color: root.palette.panel || "#171b13"
        border.color: root.palette.border || "#252b20"

        ColumnLayout {
            id: profileRow
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            Text {
                text: "DOWNLOAD PROFILE"
                color: root.palette.lime || "#c8f24f"
                font.pixelSize: 9
                font.weight: Font.Bold
                font.letterSpacing: 1.2
            }

            GridLayout {
                Layout.fillWidth: true
                columns: width < 620 ? 1 : 2
                columnSpacing: 12
                rowSpacing: 8

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text { text: "Quality preset"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox {
                        id: presetSelector
                        Layout.fillWidth: true
                        model: Object.keys(root.presets || {})
                        currentIndex: Math.max(0, model.indexOf(root.selectedPreset))
                        onActivated: root.presetChanged(currentText)
                        palette.text: root.palette.text || "#e9ece4"
                        palette.buttonText: root.palette.text || "#e9ece4"
                        palette.base: root.palette.panel2 || "#171b13"
                        palette.button: root.palette.panel2 || "#171b13"
                        background: Rectangle { radius: 8; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text { text: "Output container"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox {
                        id: outputContainer
                        Layout.fillWidth: true
                        model: ["Original", "MP4", "MKV", "WebM", "MOV", "AVI", "3GP", "TS", "MPEG", "OGV", "M4V", "MP3", "M4A", "AAC", "Opus", "OGG", "FLAC", "WAV", "AIFF", "WMA"]
                        palette.text: root.palette.text || "#e9ece4"
                        palette.buttonText: root.palette.text || "#e9ece4"
                        palette.base: root.palette.panel2 || "#171b13"
                        palette.button: root.palette.panel2 || "#171b13"
                        background: Rectangle { radius: 8; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    text: root.expanded ? "Hide advanced controls" : "Show advanced controls"
                    onClicked: root.expanded = !root.expanded
                    background: Rectangle { radius: 8; color: root.palette.panel3 || "#1d2218"; border.color: root.palette.borderHi || "#39432d" }
                    contentItem: Text { text: parent.text; color: root.palette.text || "#e9ece4"; font.pixelSize: 10; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; padding: 8 }
                }
                Button {
                    text: "Save as preset"
                    onClicked: root.savePresetRequested(JSON.stringify(root.options()))
                    background: Rectangle { radius: 8; color: "transparent"; border.color: root.palette.border || "#252b20" }
                    contentItem: Text { text: parent.text; color: root.palette.muted || "#8d9582"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; padding: 8 }
                }
                Button {
                    text: "Reset profile"
                    onClicked: root.applyPreset(root.selectedPreset, root.presets[root.selectedPreset])
                    background: Rectangle { radius: 8; color: "transparent"; border.color: root.palette.border || "#252b20" }
                    contentItem: Text { text: parent.text; color: root.palette.subtle || "#8d9582"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; padding: 8 }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: root.expanded ? "Settings below are applied to every queued URL" : "Profiles can be customized before queueing"
                    color: root.palette.subtle || "#626a59"
                    font.pixelSize: 9
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    Flow {
        visible: root.expanded
        Layout.fillWidth: true
        spacing: 7

        Repeater {
            model: [
                {key: "source", label: "Source quality"},
                {key: "encoding", label: "Video & audio"},
                {key: "details", label: "Encoder details"},
                {key: "output", label: "Subtitles & output"}
            ]
            delegate: Button {
                visible: modelData.key !== "source" || root.showSourceQuality
                text: modelData.label
                checkable: true
                checked: root.activeSection === modelData.key
                onClicked: root.activeSection = modelData.key
                implicitHeight: 36
                padding: 12
                background: Rectangle {
                    radius: 9
                    color: parent.checked ? (root.palette.lime || "#c8f24f") : (root.palette.panel || "#171b13")
                    border.color: parent.checked ? (root.palette.lime || "#c8f24f") : (root.palette.border || "#252b20")
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.checked ? "#14190b" : (root.palette.muted || "#8d9582")
                    font.pixelSize: 10
                    font.weight: parent.checked ? Font.Bold : Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    Text {
        visible: root.expanded
        Layout.fillWidth: true
        text: "Choose a section. Your changes stay active while you move between sections."
        color: root.palette.subtle || "#626a59"
        font.pixelSize: 9
        wrapMode: Text.WordWrap
    }

    Rectangle {
        visible: root.expanded && root.showSourceQuality && root.activeSection === "source"
        Layout.fillWidth: true
        implicitHeight: sourceColumn.implicitHeight + 28
        radius: 12
        color: root.palette.panel || "#171b13"
        border.color: root.palette.border || "#252b20"
        ColumnLayout {
            id: sourceColumn
            anchors.fill: parent
            anchors.margins: 15
            spacing: 7
            Text { text: "SOURCE QUALITY"; color: root.palette.lime || "#c8f24f"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.1 }
            Text { text: "Use yt-dlp format selectors to choose the source streams before FFmpeg processing."; color: root.palette.muted || "#8d9582"; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            ComboBox {
                id: sourceFormat
                Layout.fillWidth: true
                editable: true
                model: [
                    "bestvideo+bestaudio/best",
                    "best",
                    "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
                    "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
                    "bestvideo[height<=720]+bestaudio/best[height<=720]",
                    "bestvideo[height<=480]+bestaudio/best[height<=480]",
                    "bestvideo[height<=360]+bestaudio/best[height<=360]",
                    "bestaudio/best"
                ]
                editText: "bestvideo+bestaudio/best"
                palette.text: root.palette.text || "#e9ece4"
                palette.buttonText: root.palette.text || "#e9ece4"
                palette.base: root.palette.panel2 || "#171b13"
                palette.button: root.palette.panel2 || "#171b13"
                background: Rectangle { radius: 8; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" }
            }
        }
    }

    Rectangle {
        visible: root.expanded && root.activeSection === "encoding"
        Layout.fillWidth: true
        implicitHeight: encodingColumn.implicitHeight + 28
        radius: 12
        color: root.palette.panel || "#171b13"
        border.color: root.palette.border || "#252b20"
        ColumnLayout {
            id: encodingColumn
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10
            Text { text: "VIDEO & AUDIO ENCODING"; color: root.palette.lime || "#c8f24f"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.1 }
            GridLayout {
                Layout.fillWidth: true
                columns: width < 700 ? 2 : 3
                columnSpacing: 12
                rowSpacing: 9

                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Video codec"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: videoCodec; Layout.fillWidth: true; model: ["copy","h264","hevc","av1","vp9","vp8","mpeg4","mpeg2","theora"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio codec"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: audioCodec; Layout.fillWidth: true; model: ["copy","aac","mp3","opus","vorbis","flac","pcm","alac"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Rate control"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: rateControl; Layout.fillWidth: true; model: ["Source","CRF","CBR","VBR","CQ"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Video bitrate"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: videoBitrate; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && ["CBR","VBR","CQ"].indexOf(rateControl.currentText) >= 0; placeholderText: "e.g. 4500k"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio bitrate"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: audioBitrate; Layout.fillWidth: true; enabled: audioCodec.currentText !== "copy" && !["flac","pcm","alac"].includes(audioCodec.currentText); placeholderText: "e.g. 192k"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "CRF / quality (0–63)"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    SpinBox { id: qualityValue; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && ["CRF","CQ"].indexOf(rateControl.currentText) >= 0; from: 0; to: 63; value: 23; editable: true; palette.text: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Encoder preset"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: encoderPreset; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy"; model: ["ultrafast","superfast","veryfast","faster","fast","medium","slow","slower","veryslow","placebo"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Frame rate (FPS)"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: frameRate; Layout.fillWidth: true; editable: true; model: ["Source","15","20","23.976","24","25","29.97","30","48","50","59.94","60","90","120"]; editText: "Source"; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; palette.button: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Frame mode"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: frameMode; Layout.fillWidth: true; model: ["CFR","VFR"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Output resolution"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: resolution; Layout.fillWidth: true; model: ["Source","2160p","1440p","1080p","720p","540p","480p","360p","240p","Custom"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Custom resolution"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: customScale; Layout.fillWidth: true; enabled: resolution.currentText === "Custom"; placeholderText: "e.g. 1920x1080"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio sample rate"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: sampleRate; Layout.fillWidth: true; model: ["Source","22050","32000","44100","48000","96000","192000"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio channels"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: channels; Layout.fillWidth: true; model: ["Source","Mono","Stereo"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
            }
        }
    }

    Rectangle {
        visible: root.expanded && root.activeSection === "details"
        Layout.fillWidth: true
        implicitHeight: encoderColumn.implicitHeight + 28
        radius: 12
        color: root.palette.panel || "#171b13"
        border.color: root.palette.border || "#252b20"
        ColumnLayout {
            id: encoderColumn
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10
            Text { text: "ENCODER DETAILS"; color: root.palette.lime || "#c8f24f"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.1 }
            GridLayout {
                Layout.fillWidth: true
                columns: width < 700 ? 2 : 3
                columnSpacing: 12
                rowSpacing: 9
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Video encoder"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: videoEncoder; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy"; model: ["Auto","libx264","h264_nvenc","h264_qsv","h264_amf","libx265","hevc_nvenc","hevc_qsv","hevc_amf","libsvtav1","libaom-av1","av1_nvenc","libvpx-vp9","libvpx","mpeg4","mpeg2video","libtheora"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Codec profile"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: profileName; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy"; placeholderText: "e.g. high (automatic if blank)"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Codec level"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: codecLevel; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy"; placeholderText: "e.g. 4.1"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Pixel format / bit depth"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: pixelFormat; Layout.fillWidth: true; model: ["Auto","yuv420p","yuv422p","yuv444p","yuv420p10le","yuv422p10le","yuv444p10le","p010le","rgb24"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Color space"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: colorSpace; Layout.fillWidth: true; model: ["Auto","bt709","bt2020nc","smpte170m","bt470bg","smpte240m"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Color range"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: colorRange; Layout.fillWidth: true; model: ["Auto","tv","pc"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
            }
        }
    }

    Rectangle {
        visible: root.expanded && root.activeSection === "output"
        Layout.fillWidth: true
        implicitHeight: preservationColumn.implicitHeight + 28
        radius: 12
        color: root.palette.panel || "#171b13"
        border.color: root.palette.border || "#252b20"
        ColumnLayout {
            id: preservationColumn
            anchors.fill: parent
            anchors.margins: 15
            spacing: 9
            Text { text: "SUBTITLES & METADATA"; color: root.palette.lime || "#c8f24f"; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.1 }
            GridLayout {
                Layout.fillWidth: true
                columns: width < 600 ? 1 : 2
                columnSpacing: 12
                rowSpacing: 7
                CheckBox { id: subtitles; text: "Download available subtitles"; Layout.fillWidth: true; palette.text: root.palette.text || "#e9ece4" }
                CheckBox { id: automaticCaptions; text: "Include automatic captions"; Layout.fillWidth: true; palette.text: root.palette.text || "#e9ece4" }
                CheckBox { id: embedSubtitles; text: "Embed subtitles when supported"; Layout.fillWidth: true; palette.text: root.palette.text || "#e9ece4" }
                CheckBox { id: preserveMetadata; text: "Preserve metadata and chapters"; Layout.fillWidth: true; palette.text: root.palette.text || "#e9ece4" }
                CheckBox { id: saveThumbnail; text: "Download thumbnail / artwork"; Layout.fillWidth: true; palette.text: root.palette.text || "#e9ece4" }
            }
            Text {
                text: "Auto chooses an available encoder. Hardware encoders require a compatible FFmpeg build and driver. CRF is codec-specific; CBR/VBR require a video bitrate. WebM supports VP8/VP9/AV1 video and Opus/Vorbis audio."
                color: root.palette.subtle || "#626a59"
                font.pixelSize: 9
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
