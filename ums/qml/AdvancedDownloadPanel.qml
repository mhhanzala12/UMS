import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root

    property var palette: ({})
    property var presets: ({})
    property string selectedPreset: "Best Available Quality"
    property bool expanded: true
    property bool showSourceQuality: true
    property string activeSection: "source"
    readonly property string outputSummary: {
        var container = String(outputContainer.currentText || "Original")
        var audioOnly = root.isAudioOnlyContainer()
        var video = audioOnly ? "Audio export" : ("Video " + String(videoCodec.currentText || "copy").toUpperCase())
        var audio = "Audio " + String(audioCodec.currentText || "copy").toUpperCase()
        var size = audioOnly ? "" : (resolution.currentText === "Custom"
                   ? customScale.text.trim() : resolution.currentText)
        var fps = audioOnly ? "" : String(frameRate.editText || frameRate.currentText || "Source").trim()
        var parts = [container, video, audio]
        if (size && size !== "Source") parts.push(size)
        if (fps && fps !== "Source") parts.push(fps + " FPS")
        return parts.join("  ·  ")
    }
    readonly property string validationMessage: {
        var audioOnly = root.isAudioOnlyContainer()
        var video = String(videoCodec.currentText || "copy")
        if (!audioOnly && video !== "copy") {
            var mode = String(rateControl.currentText || "Source")
            var videoRate = String(videoBitrate.text || "").trim()
            if ((mode === "CBR" || mode === "VBR") && !videoRate)
                return mode + " mode needs a video bitrate, for example 2500k."
            if (videoRate && !/^\d+(?:\.\d+)?\s*[kKmMgG]?$/.test(videoRate))
                return "Video bitrate must look like 2500k, 2M, or 192k."
            if (videoRate && parseFloat(videoRate) <= 0)
                return "Video bitrate must be greater than zero."
            var profile = String(profileName.text || "").trim()
            if (profile && !/^[A-Za-z0-9_.-]{1,32}$/.test(profile))
                return "Codec profile may contain only letters, numbers, dots, underscores and hyphens."
            var level = String(codecLevel.text || "").trim()
            if (level && !/^\d{1,2}(?:\.\d{1,2})?$/.test(level))
                return "Codec level must be numeric, for example 4.1."
            if (resolution.currentText === "Custom") {
                var dimensions = /^(\d{2,5})x(\d{2,5})$/i.exec(String(customScale.text || "").trim())
                if (!dimensions)
                    return "Custom resolution must use WIDTHxHEIGHT, for example 320x240."
                var width = Number(dimensions[1]), height = Number(dimensions[2])
                if (width < 16 || height < 16 || width > 16384 || height > 16384)
                    return "Custom dimensions must be between 16 and 16384 pixels."
            }
            var fps = String(frameRate.editText || frameRate.currentText || "Source").trim()
            if (fps.toLowerCase() !== "source") {
                var rate = Number(fps)
                if (!isFinite(rate) || rate < 1 || rate > 240)
                    return "Frame rate must be Source or a number between 1 and 240."
            }
            var codec = String(videoCodec.currentText || "")
            var encoder = String(videoEncoder.currentText || "Auto")
            var families = {
                h264: ["libx264", "h264_nvenc", "h264_qsv", "h264_amf"],
                hevc: ["libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"],
                av1: ["libsvtav1", "libaom-av1", "av1_nvenc"],
                vp9: ["libvpx-vp9"], vp8: ["libvpx"],
                mpeg4: ["mpeg4"], mpeg2: ["mpeg2video"], theora: ["libtheora"]
            }
            if (encoder !== "Auto" && families[codec] && families[codec].indexOf(encoder) < 0)
                return encoder + " is not an encoder for " + codec.toUpperCase() + "."
        }
        if (root.canSetAudioBitrate()) {
            var audioRate = String(audioBitrate.text || "").trim()
            if (audioRate && !/^\d+(?:\.\d+)?\s*[kKmMgG]?$/.test(audioRate))
                return "Audio bitrate must look like 192k or 1M."
            if (audioRate && parseFloat(audioRate) <= 0)
                return "Audio bitrate must be greater than zero."
        }
        return ""
    }
    readonly property string compatibilityNotice: {
        var container = String(outputContainer.currentText || "").toLowerCase()
        if (container !== "webm" || root.isAudioOnlyContainer())
            return ""
        var notices = []
        if (videoCodec.currentText !== "copy" && ["vp8", "vp9", "av1"].indexOf(videoCodec.currentText) < 0)
            notices.push("WebM requires VP8, VP9 or AV1 video; UMS will select a compatible stream.")
        if (audioCodec.currentText !== "copy" && ["opus", "vorbis"].indexOf(audioCodec.currentText) < 0)
            notices.push("WebM requires Opus or Vorbis audio; UMS will select a compatible stream.")
        if (embedSubtitles.checked)
            notices.push("WebM subtitles are retained as sidecar files instead of being embedded.")
        return notices.join(" ")
    }

    signal presetChanged(string name)
    signal savePresetRequested(string optionsJson)

    spacing: 10

    function isAudioOnlyContainer() {
        return ["MP3", "M4A", "AAC", "OPUS", "OGG", "FLAC", "WAV", "AIFF", "WMA"]
                .indexOf(String(outputContainer.currentText || "").toUpperCase()) >= 0
    }

    function canSetAudioBitrate() {
        var audio = audioCodec.currentText
        if (audio !== "copy")
            return ["aac", "mp3", "opus", "vorbis", "wma"].indexOf(audio) >= 0
        return ["MP3", "M4A", "AAC", "OPUS", "OGG", "WMA"]
                .indexOf(String(outputContainer.currentText || "").toUpperCase()) >= 0
    }

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
        var audioOnly = root.isAudioOnlyContainer()
        var encodeVideo = !audioOnly && videoCodec.currentText !== "copy"
        var encodeAudio = audioCodec.currentText !== "copy" || audioOnly
        return {
            format: root.showSourceQuality
                   ? String(sourceFormat.editText || sourceFormat.currentText || "bestvideo+bestaudio/best").trim()
                   : "bestvideo+bestaudio/best",
            container: container === "original" ? "original" : container,
            video_codec: audioOnly ? "copy" : videoCodec.currentText,
            audio_codec: audioCodec.currentText,
            video_encoder: encodeVideo ? videoEncoder.currentText : "Auto",
            profile: encodeVideo ? profileName.text.trim() : "",
            level: encodeVideo ? codecLevel.text.trim() : "",
            pixel_format: encodeVideo ? pixelFormat.currentText : "Auto",
            color_space: encodeVideo ? colorSpace.currentText : "Auto",
            color_range: encodeVideo ? colorRange.currentText : "Auto",
            rate_control: encodeVideo ? rateControl.currentText : "Source",
            video_bitrate: encodeVideo ? videoBitrate.text.trim() : "",
            audio_bitrate: encodeAudio && root.canSetAudioBitrate() ? audioBitrate.text.trim() : "",
            crf: String(qualityValue.value),
            encoder_preset: encodeVideo ? encoderPreset.currentText : "medium",
            fps: encodeVideo ? String(frameRate.editText || frameRate.currentText || "Source").trim() : "Source",
            fps_mode: encodeVideo ? frameMode.currentText : "CFR",
            resolution: encodeVideo ? resolution.currentText : "Source",
            custom_scale: encodeVideo && resolution.currentText === "Custom" ? customScale.text.trim() : "",
            sample_rate: encodeAudio ? sampleRate.currentText : "Source",
            channels: encodeAudio ? channels.currentText : "Source",
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
                text: root.showSourceQuality ? "ADVANCED DOWNLOAD CONTROLS" : "ADVANCED CONVERSION CONTROLS"
                color: root.palette.lime || "#c8f24f"
                font.pixelSize: 9
                font.weight: Font.Bold
                font.letterSpacing: 1.2
            }
            Text {
                text: "Fine-tune source streams, output container, codecs, quality, frame rate, encoder and metadata."
                color: root.palette.muted || "#8d9582"
                font.pixelSize: 10
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
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
                    enabled: root.validationMessage.length === 0
                    onClicked: root.savePresetRequested(JSON.stringify(root.options()))
                    background: Rectangle { radius: 8; color: "transparent"; border.color: root.palette.border || "#252b20" }
                    contentItem: Text { text: parent.text; color: parent.enabled ? (root.palette.muted || "#8d9582") : (root.palette.subtle || "#626a59"); font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; padding: 8 }
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

    Rectangle {
        Layout.fillWidth: true
        radius: 11
        color: root.palette.panel || "#171b13"
        border.color: root.validationMessage.length ? "#c58b3c" : (root.compatibilityNotice.length ? "#8d7542" : root.palette.border || "#252b20")
        implicitHeight: statusColumn.implicitHeight + 22
        ColumnLayout {
            id: statusColumn
            anchors.fill: parent
            anchors.margins: 12
            spacing: 5
            Text {
                text: root.validationMessage.length ? "CHECK YOUR SETTINGS"
                      : (root.compatibilityNotice.length ? "COMPATIBILITY NOTE" : "OUTPUT SUMMARY")
                color: root.validationMessage.length ? "#e7ad58"
                      : (root.compatibilityNotice.length ? "#d8bd79" : (root.palette.lime || "#c8f24f"))
                font.pixelSize: 9
                font.weight: Font.Bold
                font.letterSpacing: 1
            }
            Text {
                text: root.validationMessage.length ? root.validationMessage
                      : (root.compatibilityNotice.length ? root.compatibilityNotice : root.outputSummary)
                color: root.palette.text || "#e9ece4"
                font.pixelSize: 10
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                visible: !root.validationMessage.length && !root.compatibilityNotice.length
                text: "These settings are applied to every supported URL added in this batch."
                color: root.palette.subtle || "#626a59"
                font.pixelSize: 9
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
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
                    ComboBox { id: videoCodec; Layout.fillWidth: true; enabled: !root.isAudioOnlyContainer(); model: ["copy","h264","hevc","av1","vp9","vp8","mpeg4","mpeg2","theora"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio codec"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: audioCodec; Layout.fillWidth: true; model: ["copy","aac","mp3","opus","vorbis","flac","pcm","alac"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Rate control"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: rateControl; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["Source","CRF","CBR","VBR","CQ"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Video bitrate"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: videoBitrate; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer() && ["CBR","VBR","CQ"].indexOf(rateControl.currentText) >= 0; placeholderText: "e.g. 4500k"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio bitrate"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: audioBitrate; Layout.fillWidth: true; enabled: root.canSetAudioBitrate(); placeholderText: "e.g. 192k"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "CRF / quality (0–63)"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    SpinBox { id: qualityValue; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer() && ["CRF","CQ"].indexOf(rateControl.currentText) >= 0; from: 0; to: 63; value: 23; editable: true; palette.text: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Encoder preset"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: encoderPreset; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["ultrafast","superfast","veryfast","faster","fast","medium","slow","slower","veryslow","placebo"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Frame rate (FPS)"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: frameRate; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); editable: true; model: ["Source","15","20","23.976","24","25","29.97","30","48","50","59.94","60","90","120"]; editText: "Source"; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; palette.button: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Frame mode"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: frameMode; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["CFR","VFR"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Output resolution"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: resolution; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["Source","2160p","1440p","1080p","720p","540p","480p","360p","240p","Custom"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Custom resolution"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: customScale; Layout.fillWidth: true; enabled: resolution.currentText === "Custom"; placeholderText: "e.g. 1920x1080"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio sample rate"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: sampleRate; Layout.fillWidth: true; enabled: audioCodec.currentText !== "copy" || root.isAudioOnlyContainer(); model: ["Source","22050","32000","44100","48000","96000","192000"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Audio channels"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: channels; Layout.fillWidth: true; enabled: audioCodec.currentText !== "copy" || root.isAudioOnlyContainer(); model: ["Source","Mono","Stereo"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
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
                    ComboBox { id: videoEncoder; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["Auto","libx264","h264_nvenc","h264_qsv","h264_amf","libx265","hevc_nvenc","hevc_qsv","hevc_amf","libsvtav1","libaom-av1","av1_nvenc","libvpx-vp9","libvpx","mpeg4","mpeg2video","libtheora"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Codec profile"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: profileName; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); placeholderText: "e.g. high (automatic if blank)"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Codec level"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    TextField { id: codecLevel; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); placeholderText: "e.g. 4.1"; palette.text: root.palette.text || "#e9ece4"; palette.base: root.palette.panel2 || "#171b13"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Pixel format / bit depth"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: pixelFormat; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["Auto","yuv420p","yuv422p","yuv444p","yuv420p10le","yuv422p10le","yuv444p10le","p010le","rgb24"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Color space"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: colorSpace; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["Auto","bt709","bt2020nc","smpte170m","bt470bg","smpte240m"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Color range"; color: root.palette.muted || "#8d9582"; font.pixelSize: 10 }
                    ComboBox { id: colorRange; Layout.fillWidth: true; enabled: videoCodec.currentText !== "copy" && !root.isAudioOnlyContainer(); model: ["Auto","tv","pc"]; palette.text: root.palette.text || "#e9ece4"; palette.buttonText: root.palette.text || "#e9ece4"; background: Rectangle { radius: 7; color: root.palette.panel2 || "#171b13"; border.color: root.palette.border || "#252b20" } }
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
