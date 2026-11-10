import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1440
    height: 900
    minimumWidth: 960
    minimumHeight: 640
    visible: true
    title: "Universal Media Studio"
    onClosing: function(close) { bridge.quit() }
    // Use native window decorations so the OS handles move, resize and snap.
    property bool customFrame: false
    flags: customFrame ? (Qt.Window | Qt.FramelessWindowHint) : Qt.Window
    color: themeColors.bg
    Behavior on color { ColorAnimation { duration: 220 } }

    property var bridge: appBridge
    property var themeColors: settingsData && settingsData.theme === "Light" ? ({
        bg: "#f2f4ed", shell: "#e8ebe1", panel: "#ffffff", panel2: "#f4f6ef",
        panel3: "#e9eddf", border: "#dce1d3", borderHi: "#a7b58b",
        text: "#20251a", muted: "#68715d", subtle: "#929a87",
        lime: "#a5d92f", limeSoft: "#c2ed60", danger: "#c64d42",
        activeBg: "#e6f1cc", hover: "#eceee4"
    }) : ({
        bg: "#0b0d0a", shell: "#090b08", panel: "#12150f", panel2: "#171b13",
        panel3: "#1d2218", border: "#252b20", borderHi: "#39432d",
        text: "#e9ece4", muted: "#8d9582", subtle: "#626a59",
        lime: "#c8f24f", limeSoft: "#d8f97a", danger: "#f0705f",
        activeBg: "#181f0f", hover: "#12150f"
    })
    property string page: "Discover"
    property string playerTitle: "Universal Media Studio"
    property string playerArtist: "Your local music workspace"
    property string playerPath: ""
    property string playerCover: ""
    property real playerVolume: 0.75
    property bool keyboardTextEntryActive: false
    property string libraryFilter: ""
    property string librarySort: "Newest"
    property string selectedPlaylist: ""
    property var selectedPlaylistItems: {
        var paths = playlistData[selectedPlaylist] || []
        return libraryItems.filter(function(row) { return paths.indexOf(row.path) >= 0 })
    }
    property var filteredLibraryItems: {
        var rows = libraryItems.filter(function(row) {
            var query = libraryFilter.trim().toLowerCase()
            return !query || [row.title, row.artist, row.album].join(" ").toLowerCase().indexOf(query) >= 0
        })
        rows.sort(function(a, b) {
            if (librarySort === "Title") return (a.title || "").localeCompare(b.title || "")
            if (librarySort === "Artist") return (a.artist || "").localeCompare(b.artist || "")
            return (b.modified || 0) - (a.modified || 0)
        })
        return rows
    }
    // Keep QML delegates bounded for large libraries and long playlists.
    property int libraryPageSize: 100
    property int playlistPageSize: 100
    property var visibleLibraryItems: filteredLibraryItems.slice(0, libraryPageSize)
    property var visiblePlaylistItems: selectedPlaylistItems.slice(0, playlistPageSize)
    onSelectedPlaylistChanged: playlistPageSize = 100
    property int playerPosition: 0
    property int playerDuration: 0
    property bool playerPlaying: false
    property bool playerMuted: false
    property bool playerCanSkip: false
    property bool playerShuffle: false
    property int playerRepeat: 0
    readonly property bool hasTrack: playerPath.length > 0
    property var recentSearches: (settingsData && settingsData.recent_searches) ? settingsData.recent_searches : []
    property string searchQuery: ""
    property string searchKind: "All"
    property string spotifyUrl: ""
    property string presetName: "Best Available Quality"
    property string conversionPresetName: "Balanced Quality and Size"
    property var presets: JSON.parse(bridge.presetsJson())
    property var queueItems: JSON.parse(bridge.queueJson())
    property var settingsData: JSON.parse(bridge.settingsJson())
    property var searchItems: []
    property var libraryItems: []
    property var playlistData: ({})
    property var diagnosticsData: JSON.parse(bridge.statusJson())
    property var browserProfiles: []
    property var selectedTrack: ({})
    property bool analysisBusy: false
    property string analysisError: ""
    property string analysisTargetUrl: ""
    property string applicationLogText: ""
    property var analysisData: ({})
    property var analysisThumbnailList: []
    property int analysisThumbnailIndex: 0
    property string lyricsTitle: ""
    property string lyricsArtist: ""
    property string lyricsRequestedTitle: ""
    property string lyricsRequestedArtist: ""
    property string lyricsMessage: ""
    property string lyricsSource: ""
    property string lyricsTrackPath: ""
    property bool lyricsTimed: false
    property bool lyricsSynchronized: false
    property var lyricsLines: []

    function formatMediaDuration(value) {
        if (value === null || value === undefined || value === "") return "—"
        var seconds = Math.max(0, Math.floor(Number(value) || 0))
        var hours = Math.floor(seconds / 3600)
        var minutes = Math.floor((seconds % 3600) / 60)
        var remainder = seconds % 60
        return hours > 0
                ? (hours + ":" + (minutes < 10 ? "0" : "") + minutes + ":" + (remainder < 10 ? "0" : "") + remainder)
                : (minutes + ":" + (remainder < 10 ? "0" : "") + remainder)
    }
    function displayCount(value) {
        if (value === null || value === undefined || value === "") return "—"
        var number = Number(value)
        return isNaN(number) ? String(value) : number.toLocaleString()
    }
    function displayMediaDate(value) {
        var date = String(value || "")
        return date.length === 8 && /^\d{8}$/.test(date)
                ? date.slice(0, 4) + "-" + date.slice(4, 6) + "-" + date.slice(6, 8)
                : (date || "—")
    }
    function displayMediaSize(value) {
        var bytes = Number(value)
        if (!isFinite(bytes) || bytes <= 0) return "—"
        var units = ["B", "KB", "MB", "GB", "TB"]
        var index = 0
        while (bytes >= 1024 && index < units.length - 1) {
            bytes /= 1024
            index++
        }
        return (index === 0 ? Math.round(bytes) : bytes.toFixed(bytes >= 100 ? 0 : 1)) + " " + units[index]
    }
    function buildAnalysisThumbnailList(data) {
        var urls = []
        if (data && data.thumbnail) urls.push(String(data.thumbnail))
        var variants = data && data.thumbnails ? data.thumbnails : []
        for (var i = 0; i < variants.length; i++) {
            var value = typeof variants[i] === "string" ? variants[i] : variants[i].url
            if (value && urls.indexOf(String(value)) < 0) urls.push(String(value))
        }
        return urls
    }
    function normalizeTrackText(value) {
        return String(value || "").toLowerCase()
                .replace(/\([^)]*\)/g, " ")
                .replace(/\b(feat|ft|featuring)\.?\b.*$/g, " ")
                .replace(/[^a-z0-9]+/g, " ")
                .trim()
    }
    function refreshLyricsSyncState() {
        // The lyrics request is initiated for the currently loaded player item.
        // Use its stable source path as identity instead of comparing display
        // metadata, which may differ because of tags, punctuation or suffixes.
        var sameTrack = lyricsTrackPath.length > 0
                && playerPath.length > 0
                && lyricsTrackPath === playerPath
        lyricsSynchronized = lyricsTimed && sameTrack
        if (lyricsTimed && !sameTrack)
            lyricsMessage = "Timed lyrics belong to a different track than the one currently loaded."
    }

    function refreshState() {
        queueItems = JSON.parse(bridge.queueJson())
        presets = JSON.parse(bridge.presetsJson())
        settingsData = JSON.parse(bridge.settingsJson())
    }
    function setPage(value) {
        if (page === value) return
        page = value
        pageStack.replace(pageComponent(value))
        if (value === "Library") bridge.refreshLibrary()
        if (value === "Playlists") bridge.refreshPlaylists()
        if (value === "Settings") { bridge.diagnostics(); bridge.refreshBrowserProfiles() }
    }
    function pageComponent(value) {
        if (value === "Discover") return discoverPage
        if (value === "Downloader") return downloaderPage
        if (value === "Downloads") return downloadsPage
        if (value === "Library") return libraryPage
        if (value === "Playlists") return playlistsPage
        if (value === "Converter") return converterPage
        if (value === "Settings") return settingsPage
        return discoverPage
    }
    // ── Search / detail / downloads helpers ──────────────────────────
    function providerColor(p) {
        if (p === "Deezer") return "#a238ff"
        if (p === "Apple Music") return "#fa4a5e"
        if (p === "YouTube") return "#ff3b30"
        if (p === "SoundCloud") return "#ff7a00"
        return themeColors.lime
    }
    function providerLabel(p) { return p === "Apple Music" ? "Apple" : p }
    function kindLabel(k) { return k === "Tracks" ? "Track" : (k === "Albums" ? "Album" : (k === "Playlists" ? "Playlist" : (k === "Artists" ? "Artist" : k))) }
    function kindIcon(k) { return k === "Tracks" ? "music" : (k === "Albums" ? "disc" : (k === "Playlists" ? "playlist" : "user")) }
    function searchCount(kind) { return searchItems.filter(function(r) { return (r.kind || "Tracks") === kind }).length }
    function detailMeta() {
        if (!detailData) return ""
        var n = detailData.tracks.length
        var secs = 0
        for (var i = 0; i < n; i++) secs += detailData.tracks[i].duration || 0
        var parts = [detailData.subtitle]
        if (n > 0) parts.push(n + (n === 1 ? " track" : " tracks"))
        if (secs > 0) parts.push(Math.max(1, Math.round(secs / 60)) + " min")
        return parts.filter(function(v) { return v }).join("  ·  ")
    }
    function openResult(row) {
        var kind = row.kind || "Tracks"
        detailData = { kind: kind, title: row.title, subtitle: row.artist, cover: row.cover || "", url: row.url || "", tracks: kind === "Tracks" ? [row] : [] }
        detailLoading = kind !== "Tracks"
        if (kind !== "Tracks") bridge.openCollection(kind, row.url || "")
    }
    function playDetail(start) {
        if (!detailData || !detailData.tracks.length) return
        bridge.playPreviewList(JSON.stringify(detailData.tracks), start || 0)
    }
    function downloadDetail() {
        if (!detailData || !detailData.tracks.length) return
        if (detailData.kind === "Tracks") {
            var t = detailData.tracks[0]
            bridge.enqueueMusicResult(t.title, t.artist, t.cover || "")
            toast.showMessage("Added to downloads.")
        } else {
            bridge.enqueueCollection(JSON.stringify({ name: detailData.title, cover: detailData.cover, tracks: detailData.tracks }))
        }
    }
    function syncListModel(model, items) {
        for (var i = 0; i < items.length; i++) {
            if (i < model.count) model.set(i, items[i])
            else model.append(items[i])
        }
        while (model.count > items.length) model.remove(model.count - 1)
    }
    function rebuildDownloads() {
        var map = {}, order = []
        for (var i = 0; i < queueItems.length; i++) {
            var t = queueItems[i]
            var mt = t.music_track || {}
            var gid = t.group_id || ("task-" + t.id)
            var g = map[gid]
            if (!g) {
                g = { gid: gid, grouped: !!t.group_id,
                      name: t.group_name || (mt.title ? ((mt.artist ? mt.artist + " — " : "") + mt.title) : String(t.name || "Download")),
                      cover: t.group_cover || mt.cover || t.thumbnail || "",
                      uploader: t.uploader || mt.artist || "",
                      duration: t.duration || mt.duration || 0,
                      total: 0, done: 0, failed: 0, active: 0, cancelled: 0, pctSum: 0, errorText: "", signIn: false, rows: [] }
                map[gid] = g
                order.push(gid)
            }
            var detail = String(t.detail || "")
            g.total++
            if (t.status === "Completed") g.done++
            else if (t.status === "Failed") {
                g.failed++
                if (!g.errorText) g.errorText = detail
                if (/sign.?in|cookies|confirm you/i.test(detail)) g.signIn = true
            }
            else if (t.status === "Cancelled") g.cancelled++
            else g.active++
            g.pctSum += (t.status === "Completed" ? 100 : (t.progress || 0))
            var folder = (t.outputs && t.outputs.length) ? String(t.outputs[0]).replace(/[\\\/][^\\\/]*$/, "") : ""
            g.rows.push({ tid: String(t.id), title: String(mt.title || t.name || ""), artist: String(mt.artist || ""),
                          status: String(t.status), progress: t.progress || 0, detail: detail, folder: folder })
        }
        var all = order.map(function(k) { return map[k] })
        downloadCounts = {
            all: all.length,
            active: all.filter(function(g) { return g.active > 0 }).length,
            done: all.filter(function(g) { return g.active === 0 }).length
        }
        var shown = all.filter(function(g) {
            return downloadTab === "All" || (downloadTab === "Downloading" && g.active > 0) || (downloadTab === "Completed" && g.active === 0)
        })
        syncListModel(downloadGroupsModel, shown.map(function(g) {
            return { gid: g.gid, grouped: g.grouped, name: g.name, cover: g.cover,
                     uploader: g.uploader, duration: g.duration, total: g.total, done: g.done,
                     failed: g.failed, active: g.active, cancelled: g.cancelled, pct: Math.round(g.pctSum / Math.max(1, g.total)),
                     errorText: g.errorText, signIn: g.signIn, rowsJson: JSON.stringify(g.rows) }
        }))
    }
    onDownloadTabChanged: rebuildDownloads()
    ListModel { id: downloadGroupsModel }

    function toggleMaximize() {
        if (window.visibility === Window.Maximized) window.showNormal()
        else window.showMaximized()
    }
    function runSearch(text, provider) {
        text = (text || "").trim()
        if (!text.length) return
        var list = [text].concat(recentSearches.filter(function(x) { return x !== text })).slice(0, 8)
        bridge.setRecentSearches(JSON.stringify(list))
        if (text.indexOf("spotify.com/") >= 0 || text.indexOf("spotify:") === 0) {
            bridge.enqueueSpotify(text)
            return
        }
        searchQuery = text
        searchKind = "All"
        searchTab = "All"
        detailData = null
        detailLoading = false
        searchItems = []
        searchBusy = true
        bridge.searchMusic(text, provider || "All catalogs", "All")
        setPage("Discover")
    }
    function formatDuration(seconds) {
        if (!seconds || seconds < 0) return "—"
        var m = Math.floor(seconds / 60)
        var s = Math.floor(seconds % 60)
        return m + ":" + (s < 10 ? "0" : "") + s
    }
    function formatBytes(value) {
        if (!value) return "Size unknown"
        if (value > 1073741824) return (value / 1073741824).toFixed(1) + " GB"
        if (value > 1048576) return (value / 1048576).toFixed(1) + " MB"
        return Math.round(value / 1024) + " KB"
    }

    Component.onCompleted: {
        rebuildDownloads()
        pageStack.replace(discoverPage)
        startupTimer.start()
    }
    // Library scan, playlists and tool probing run shortly after the first frame so
    // they never compete with QML loading.
    Timer {
        id: startupTimer
        interval: 350
        repeat: false
        onTriggered: {
            bridge.finishStartup()
            bridge.refreshLibrary()
            bridge.refreshPlaylists()
        }
    }
    Connections {
        target: bridge
        function onQueueChanged() { queueItems = JSON.parse(bridge.queueJson())
 rebuildDownloads() }
        function onLogUpdated() {
            if (logDialog.visible)
                applicationLogText = bridge.readLog()
        }
        function onPresetsChanged(value) { presets = JSON.parse(value) }
        function onSettingsChanged(value) { settingsData = JSON.parse(value) }
        function onSearchResults(value) { searchItems = JSON.parse(value) }
        function onSearchFinished() { searchBusy = false }
        function onCollectionReady(value) {
            detailLoading = false
            if (!value) { detailData = null; return }
            if (detailData) detailData = JSON.parse(value)
        }
        function onLibraryChanged(value) { libraryItems = JSON.parse(value) }
        function onConversionSourceSelected(value) { conversionSource.text = value }
        function onPlaylistsChanged(value) { playlistData = JSON.parse(value) }
        function onLyricsReady(value) {
            try {
                var payload = JSON.parse(value)
                lyricsLines = payload.lines || []
                lyricsTitle = payload.title || playerTitle
                lyricsArtist = payload.artist || playerArtist
                lyricsRequestedTitle = payload.request_title || lyricsTitle
                lyricsRequestedArtist = payload.request_artist || lyricsArtist
                lyricsTrackPath = payload.track_path || ""
                lyricsTimed = payload.synchronized === true
                lyricsSource = payload.source || ""
                lyricsMessage = payload.message || ""
                refreshLyricsSyncState()
                lyricsDialog.open()
            } catch (error) {
                toast.showMessage("Lyrics could not be displayed.", true)
            }
        }
        function onPlayerChanged(value) {
            var data = JSON.parse(value)
            if (data.song && data.song.path) { playerTitle = data.song.title || "Unknown track"
 playerArtist = data.song.artist || "Local library"
 playerPath = data.song.path || ""
 playerCover = data.song.cover || ""
 selectedTrack = data.song }
            if (data.closed === true) { playerPath = ""; playerCover = ""; selectedTrack = ({}); playerPosition = 0; playerDuration = 0; playerPlaying = false }
            if (data.shuffle !== undefined) playerShuffle = data.shuffle
            if (data.repeat !== undefined) playerRepeat = data.repeat
            if (data.volume !== undefined) playerVolume = data.volume
            if (data.muted !== undefined) playerMuted = data.muted
            if (data.can_skip !== undefined) playerCanSkip = data.can_skip
            if (data.position !== undefined) playerPosition = data.position
            if (data.duration !== undefined) playerDuration = data.duration
            if (data.state !== undefined) playerPlaying = data.state === 1
            refreshLyricsSyncState()
        }
        function onAnalysisReady(value) {
            try {
                analysisData = JSON.parse(value)
                analysisThumbnailList = buildAnalysisThumbnailList(analysisData)
                analysisThumbnailIndex = 0
                analysisError = ""
                analysisBusy = false
                analysisDialog.open()
            } catch (error) {
                analysisData = ({})
                analysisThumbnailList = []
                analysisBusy = false
                analysisError = "The source returned invalid metadata. Please analyze the URL again."
                analysisDialog.open()
            }
        }
        function onAnalysisFailed(value) {
            analysisBusy = false
            analysisData = ({})
            analysisThumbnailList = []
            analysisError = String(value || "The source could not be analyzed.")
            analysisDialog.open()
        }
        function onStatusChanged(value) {
            try {
                var data = JSON.parse(value)
                if (data.analysis) {
                    analysisBusy = true
                    analysisError = ""
                    analysisData = ({})
                    analysisDialog.open()
                }
                if (data.spotify) toast.showMessage(data.spotify)
                if (data.yt_dlp) diagnosticsData = data
                if (data.browser_profiles) browserProfiles = data.browser_profiles
            } catch (e) {}
        }
        function onErrorRaised(value) { searchBusy = false
 toast.showMessage(value, true) }
    }
    property bool searchBusy: false
    property string searchTab: "All"
    property var detailData: null
    property bool detailLoading: false
    property string downloadTab: "All"
    property var downloadCounts: ({ all: 0, active: 0, done: 0 })
    property bool playlistNewOpen: false
    property var visibleSearchRows: {
        var out = []
        var kinds = ["Tracks", "Artists", "Albums", "Playlists"]
        for (var k = 0; k < kinds.length; k++) {
            if (searchTab !== "All" && searchTab !== kinds[k]) continue
            var rows = searchItems.filter(function(r) { return (r.kind || "Tracks") === kinds[k] })
            if (!rows.length) continue
            if (searchTab === "All") out.push({ header: true, kind: kinds[k], count: rows.length })
            for (var i = 0; i < rows.length; i++) out.push({ header: false, row: rows[i] })
        }
        return out
    }

    header: Rectangle {
        id: titleBar
        height: 40
        color: themeColors.bg
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: themeColors.border }
        DragHandler {
            target: null
            enabled: customFrame
            onActiveChanged: if (active) window.startSystemMove()
        }
        TapHandler {
            enabled: customFrame
            acceptedButtons: Qt.LeftButton
            onDoubleTapped: window.toggleMaximize()
        }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(384, parent.width - 320)
            height: 26
            radius: 13
            color: themeColors.panel
            border.color: globalSearch.activeFocus ? themeColors.borderHi : themeColors.border
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 11
                anchors.rightMargin: 9
                spacing: 7
                Icon { name: "search"; color: themeColors.muted; implicitWidth: 13; implicitHeight: 13; strokeWidth: 1.4 }
                TextField {
                    id: globalSearch
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    placeholderText: "Search or paste link…"
                    color: themeColors.text
                    placeholderTextColor: themeColors.muted
                    background: null
                    font.pixelSize: 11
                    verticalAlignment: TextInput.AlignVCenter
                    topPadding: 0; bottomPadding: 0; leftPadding: 0
                    onAccepted: { window.runSearch(text); text = "" }
                }
                Rectangle {
                    width: ctrlK.implicitWidth + 10; height: 15; radius: 4
                    color: themeColors.panel2; border.color: themeColors.border
                    Text { id: ctrlK; anchors.centerIn: parent; text: "Ctrl+K"; color: themeColors.subtle; font.pixelSize: 8; font.family: "monospace" }
                }
            }
        }
        Row {
            visible: customFrame
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            Repeater {
                model: [
                    { icon: "minimize", action: "min" },
                    { icon: "maximize", action: "max" },
                    { icon: "close", action: "close" }
                ]
                delegate: Rectangle {
                    width: 46; height: titleBar.height
                    color: ctrlMouse.containsMouse ? (modelData.action === "close" ? "#c42b1c" : themeColors.panel2) : "transparent"
                    Icon {
                        anchors.centerIn: parent
                        name: modelData.action === "max" && window.visibility === Window.Maximized ? "restore" : modelData.icon
                        color: ctrlMouse.containsMouse && modelData.action === "close" ? "#ffffff" : themeColors.muted
                        implicitWidth: 12; implicitHeight: 12; strokeWidth: 1.35
                    }
                    MouseArea {
                        id: ctrlMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (modelData.action === "min") window.showMinimized()
                            else if (modelData.action === "max") window.toggleMaximize()
                            else { window.close() }
                        }
                    }
                }
            }
        }
    }

    Shortcut { sequence: "Ctrl+K"; onActivated: globalSearch.forceActiveFocus() }
    Shortcut {
        sequence: "Space"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive
        onActivated: bridge.togglePlayback()
    }
    Shortcut {
        sequence: "Ctrl+Right"
        context: Qt.WindowShortcut
        enabled: window.playerCanSkip && !window.keyboardTextEntryActive
        onActivated: bridge.playNext()
    }
    Shortcut {
        sequence: "Ctrl+Left"
        context: Qt.WindowShortcut
        enabled: window.playerCanSkip && !window.keyboardTextEntryActive
        onActivated: bridge.playPrevious()
    }
    Shortcut {
        sequence: "Ctrl+L"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive
        onActivated: bridge.findCurrentLyrics()
    }
    Shortcut {
        sequence: "M"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive
        onActivated: bridge.toggleMute()
    }
    Shortcut {
        sequence: "Shift+Right"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive && window.playerDuration > 0
        onActivated: bridge.seekPlayer(Math.min(window.playerDuration, window.playerPosition + 5000))
    }
    Shortcut {
        sequence: "Shift+Left"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive
        onActivated: bridge.seekPlayer(Math.max(0, window.playerPosition - 5000))
    }
    Shortcut {
        sequence: "Ctrl+Up"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive
        onActivated: bridge.setVolume(Math.min(1.0, window.playerVolume + 0.05))
    }
    Shortcut {
        sequence: "Ctrl+Down"
        context: Qt.WindowShortcut
        enabled: window.hasTrack && !window.keyboardTextEntryActive
        onActivated: bridge.setVolume(Math.max(0.0, window.playerVolume - 0.05))
    }

    // Edge grips so the frameless window can still be resized.
    component EdgeGrip: MouseArea {
        property int edges: 0
        hoverEnabled: true
        z: 1000
        visible: window.customFrame && window.visibility === Window.Windowed
        onPressed: window.startSystemResize(edges)
    }
    EdgeGrip { edges: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.topMargin: 8; anchors.bottomMargin: 8; width: 4 }
    EdgeGrip { edges: Qt.RightEdge; cursorShape: Qt.SizeHorCursor; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.topMargin: 8; anchors.bottomMargin: 8; width: 4 }
    EdgeGrip { edges: Qt.TopEdge; cursorShape: Qt.SizeVerCursor; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 8; anchors.rightMargin: 8; height: 4 }
    EdgeGrip { edges: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 8; anchors.rightMargin: 8; height: 4 }
    EdgeGrip { edges: Qt.LeftEdge | Qt.TopEdge; cursorShape: Qt.SizeFDiagCursor; anchors.left: parent.left; anchors.top: parent.top; width: 8; height: 8 }
    EdgeGrip { edges: Qt.RightEdge | Qt.BottomEdge; cursorShape: Qt.SizeFDiagCursor; anchors.right: parent.right; anchors.bottom: parent.bottom; width: 8; height: 8 }
    EdgeGrip { edges: Qt.RightEdge | Qt.TopEdge; cursorShape: Qt.SizeBDiagCursor; anchors.right: parent.right; anchors.top: parent.top; width: 8; height: 8 }
    EdgeGrip { edges: Qt.LeftEdge | Qt.BottomEdge; cursorShape: Qt.SizeBDiagCursor; anchors.left: parent.left; anchors.bottom: parent.bottom; width: 8; height: 8 }

    // ── Shared building blocks ───────────────────────────────────────
    component Btn: Rectangle {
        id: btn
        property string text: ""
        property string icon: ""
        property bool primary: false
        property bool danger: false
        signal clicked()
        implicitHeight: 36
        implicitWidth: btnRow.implicitWidth + 30
        radius: 10
        opacity: enabled ? 1 : 0.5
        color: primary ? (btnArea.containsMouse ? window.themeColors.limeSoft : window.themeColors.lime)
                       : (btnArea.containsMouse ? window.themeColors.panel2 : "transparent")
        border.color: primary ? "transparent" : (danger ? window.themeColors.danger : (btnArea.containsMouse ? window.themeColors.borderHi : window.themeColors.border))
        scale: btnArea.pressed ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        RowLayout {
            id: btnRow
            anchors.centerIn: parent
            spacing: 7
            Icon {
                visible: btn.icon.length > 0
                name: btn.icon
                color: btn.primary ? "#14190b" : (btn.danger ? window.themeColors.danger : window.themeColors.text)
                implicitWidth: 14; implicitHeight: 14
            }
            Text {
                visible: btn.text.length > 0
                text: btn.text
                font.pixelSize: 12
                font.weight: Font.DemiBold
                color: btn.primary ? "#14190b" : (btn.danger ? window.themeColors.danger : window.themeColors.text)
            }
        }
        MouseArea { id: btnArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; enabled: btn.enabled; onClicked: btn.clicked() }
    }

    component SquareButton: Rectangle {
        id: sq
        property string icon: "play"
        property bool accent: false
        property real glyph: 14
        signal clicked()
        implicitWidth: 32
        implicitHeight: 32
        radius: 8
        color: sqArea.containsMouse ? window.themeColors.panel2 : "transparent"
        border.color: sqArea.containsMouse ? window.themeColors.borderHi : window.themeColors.border
        Icon {
            anchors.centerIn: parent
            name: sq.icon
            color: sq.accent ? window.themeColors.lime : window.themeColors.muted
            implicitWidth: sq.glyph; implicitHeight: sq.glyph
        }
        MouseArea { id: sqArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: sq.clicked() }
    }

    component Segmented: Rectangle {
        id: seg
        property var options: []
        property string current: ""
        signal picked(string value)
        implicitHeight: 34
        implicitWidth: segRow.implicitWidth + 8
        radius: 10
        color: window.themeColors.bg
        border.color: window.themeColors.border
        Row {
            id: segRow
            anchors.centerIn: parent
            spacing: 2
            Repeater {
                model: seg.options
                delegate: Rectangle {
                    height: 26
                    width: segLabel.implicitWidth + 24
                    radius: 7
                    color: seg.current === modelData ? window.themeColors.panel3 : "transparent"
                    Text {
                        id: segLabel
                        anchors.centerIn: parent
                        text: modelData
                        font.pixelSize: 11
                        font.weight: seg.current === modelData ? Font.Bold : Font.Medium
                        color: seg.current === modelData ? window.themeColors.text : window.themeColors.muted
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: seg.picked(modelData) }
                }
            }
        }
    }

    component StyledCombo: ComboBox {
        id: cb
        implicitHeight: 36
        implicitWidth: 176
        font.pixelSize: 12
        background: Rectangle {
            radius: 9
            color: window.themeColors.bg
            border.color: cb.popup.visible || cb.hovered ? window.themeColors.borderHi : window.themeColors.border
        }
        contentItem: Text {
            leftPadding: 12; rightPadding: 30
            text: cb.displayText
            color: window.themeColors.text
            font.pixelSize: 12
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Icon {
            x: cb.width - width - 12
            y: (cb.height - height) / 2
            name: cb.popup.visible ? "chevron-up" : "chevron-down"
            color: window.themeColors.muted
            implicitWidth: 14; implicitHeight: 14
        }
        delegate: ItemDelegate {
            width: cb.width - 8
            height: 34
            padding: 0
            contentItem: RowLayout {
                spacing: 6
                Text {
                    Layout.fillWidth: true
                    leftPadding: 10
                    text: cb.textAt(index)
                    color: cb.currentIndex === index ? window.themeColors.lime : window.themeColors.text
                    font.pixelSize: 12
                    font.weight: cb.currentIndex === index ? Font.Bold : Font.Medium
                    elide: Text.ElideRight
                }
                Icon { visible: cb.currentIndex === index; name: "check"; color: window.themeColors.lime; implicitWidth: 14; implicitHeight: 14; Layout.rightMargin: 10 }
            }
            background: Rectangle { radius: 7; color: parent.hovered ? window.themeColors.panel2 : "transparent" }
        }
        popup: Popup {
            y: cb.height + 4
            width: cb.width
            padding: 4
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 280)
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: cb.popup.visible ? cb.delegateModel : null
                currentIndex: cb.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator {}
            }
            background: Rectangle { radius: 10; color: window.themeColors.panel; border.color: window.themeColors.borderHi }
        }
    }

    component SettingsCard: Rectangle {
        id: card
        property string icon: "settings"
        property string title: ""
        property string description: ""
        default property alias content: cardBody.data
        property alias trailing: trailingSlot.data
        Layout.fillWidth: true
        radius: 16
        color: window.themeColors.panel
        border.color: window.themeColors.border
        implicitHeight: cardCol.implicitHeight + 44
        ColumnLayout {
            id: cardCol
            anchors.fill: parent
            anchors.margins: 22
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 30; Layout.preferredHeight: 30
                    radius: 9; color: window.themeColors.activeBg; border.color: window.themeColors.borderHi
                    Icon { anchors.centerIn: parent; name: card.icon; color: window.themeColors.lime; implicitWidth: 15; implicitHeight: 15 }
                }
                Text { text: card.title.toUpperCase(); color: window.themeColors.text; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 0.6 }
                Item { Layout.fillWidth: true }
                RowLayout { id: trailingSlot; spacing: 8 }
            }
            Text {
                visible: card.description.length > 0
                Layout.fillWidth: true
                Layout.maximumWidth: 620
                text: card.description
                color: window.themeColors.muted
                font.pixelSize: 12
                lineHeight: 1.25
                wrapMode: Text.WordWrap
            }
            ColumnLayout { id: cardBody; Layout.fillWidth: true; spacing: 12 }
        }
    }

    component CoverBox: Rectangle {
        property string source: ""
        property real box: 42
        property real corner: 6
        property string fallback: "music"
        implicitWidth: box
        implicitHeight: box
        radius: corner
        color: window.themeColors.panel3
        clip: true
        Image { anchors.fill: parent; source: parent.source; sourceSize.width: parent.box * 2; sourceSize.height: parent.box * 2; fillMode: Image.PreserveAspectCrop; asynchronous: true }
        Icon { anchors.centerIn: parent; visible: parent.source.length === 0; name: parent.fallback; color: window.themeColors.lime; implicitWidth: parent.box * 0.42; implicitHeight: parent.box * 0.42 }
    }

    component ProviderChip: Rectangle {
        property string provider: ""
        implicitHeight: 22
        implicitWidth: provRow.implicitWidth + 20
        radius: 11
        color: window.themeColors.panel2
        border.color: window.themeColors.border
        Row {
            id: provRow
            anchors.centerIn: parent
            spacing: 6
            Rectangle { width: 6; height: 6; radius: 3; anchors.verticalCenter: parent.verticalCenter; color: window.providerColor(provider) }
            Text { text: window.providerLabel(provider); color: window.themeColors.muted; font.pixelSize: 10; font.weight: Font.DemiBold }
        }
    }

    component EmptyState: ColumnLayout {
        property string icon: "download"
        property string title: ""
        property string body: ""
        spacing: 10
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 56; Layout.preferredHeight: 56
            radius: 14; color: window.themeColors.panel; border.color: window.themeColors.border
            Icon { anchors.centerIn: parent; name: parent.parent.icon; color: window.themeColors.muted; implicitWidth: 22; implicitHeight: 22 }
        }
        Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 6; text: parent.title; color: window.themeColors.text; font.pixelSize: 14; font.weight: Font.Bold }
        Text {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 340
            horizontalAlignment: Text.AlignHCenter
            text: parent.body
            color: window.themeColors.muted
            font.pixelSize: 12
            lineHeight: 1.3
            wrapMode: Text.WordWrap
        }
    }

    // Small icon-only button used by the player bar.
    component BarButton: Item {
        id: barBtn
        property string icon: "play"
        property bool active: false
        property real glyph: 17
        property color tint: window.themeColors.muted
        signal clicked()
        implicitWidth: 32
        implicitHeight: 32
        opacity: enabled ? 1 : 0.4
        Rectangle { anchors.fill: parent; radius: 8; color: barArea.containsMouse && barBtn.enabled ? window.themeColors.panel2 : "transparent" }
        Icon {
            anchors.centerIn: parent
            name: barBtn.icon
            color: barBtn.active ? window.themeColors.lime : barArea.containsMouse ? window.themeColors.text : barBtn.tint
            implicitWidth: barBtn.glyph; implicitHeight: barBtn.glyph
        }
        MouseArea { id: barArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; enabled: barBtn.enabled; onClicked: barBtn.clicked() }
    }

    RowLayout {
        anchors.fill: parent
        anchors.bottomMargin: playerDock.height
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 232
            Layout.fillHeight: true
            color: themeColors.bg
            Rectangle { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right; width: 1; color: themeColors.border }
            ColumnLayout {
                anchors.fill: parent
                anchors.rightMargin: 1
                spacing: 0

                // Brand
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 12
                        spacing: 10
                        Rectangle {
                            width: 36; height: 36; radius: 11
                            color: themeColors.lime
                            Icon { anchors.centerIn: parent; name: "audio"; color: "#151a0d"; implicitWidth: 20; implicitHeight: 20; strokeWidth: 2.2 }
                        }
                        ColumnLayout {
                            spacing: 1
                            RowLayout {
                                spacing: 6
                                Text { text: "Fox's Media Studio"; color: themeColors.text; font.pixelSize: 13; font.weight: Font.Bold }
                                Rectangle {
                                    width: verBadge.implicitWidth + 10; height: 15; radius: 4
                                    color: themeColors.activeBg; border.color: themeColors.borderHi
                                    Text { id: verBadge; anchors.centerIn: parent; text: "UMS"; color: themeColors.lime; font.pixelSize: 8; font.weight: Font.Bold }
                                }
                            }
                            Text { text: "Everything Downloader"; color: themeColors.subtle; font.pixelSize: 10 }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: themeColors.border; Layout.topMargin: 12 }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    Layout.topMargin: 12
                    spacing: 4
                    Repeater {
                        model: [
                            {name:"Discover", label:"Search & Explore", icon:"search"},
                            {name:"Downloader", label:"Downloader", icon:"link"},
                            {name:"Downloads", label:"Downloads", icon:"download"},
                            {name:"Library", label:"Library", icon:"library"},
                            {name:"Playlists", label:"Playlists", icon:"playlist"},
                            {name:"Converter", label:"Converter", icon:"convert"},
                            {name:"Settings", label:"Settings", icon:"settings"}
                        ]
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 40
                            radius: 9
                            readonly property bool current: page === modelData.name
                            color: current ? themeColors.activeBg : navMouse.containsMouse ? themeColors.hover : "transparent"
                            border.color: current ? themeColors.borderHi : "transparent"
                            Rectangle {
                                width: 3; radius: 2; color: themeColors.lime
                                anchors.left: parent.left; anchors.leftMargin: 1
                                anchors.top: parent.top; anchors.topMargin: 6
                                anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                                opacity: current ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14; anchors.rightMargin: 12
                                spacing: 12
                                Icon { name: modelData.icon; color: current ? themeColors.lime : themeColors.muted; implicitWidth: 16; implicitHeight: 16; strokeWidth: 1.9 }
                                Text { text: modelData.label; color: current ? themeColors.text : themeColors.muted; font.pixelSize: 12; font.weight: current ? Font.DemiBold : Font.Medium }
                                Item { Layout.fillWidth: true }
                                Rectangle {
                                    readonly property int pending: downloadCounts.all
                                    visible: modelData.name === "Downloads" && pending > 0
                                    width: Math.max(20, badgeText.implicitWidth + 12); height: 18; radius: 9
                                    color: themeColors.panel3
                                    Text { id: badgeText; anchors.centerIn: parent; text: parent.pending; color: themeColors.muted; font.pixelSize: 10; font.weight: Font.DemiBold }
                                }
                            }
                            MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: setPage(modelData.name) }
                            Behavior on color { ColorAnimation { duration: 160 } }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // Mini now-playing card
                Rectangle {
                    visible: hasTrack
                    Layout.fillWidth: true
                    Layout.leftMargin: 10; Layout.rightMargin: 10; Layout.bottomMargin: 10
                    Layout.preferredHeight: 62
                    radius: 14
                    color: themeColors.panel
                    border.color: themeColors.border
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10; anchors.rightMargin: 10
                        spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 40; Layout.preferredHeight: 40
                            radius: 8; color: themeColors.panel3; clip: true
                            Image { anchors.fill: parent; source: selectedTrack.cover || ""; sourceSize.width: 96; sourceSize.height: 96; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                            Icon { anchors.centerIn: parent; name: "music"; color: themeColors.lime; visible: !selectedTrack.cover; implicitWidth: 18; implicitHeight: 18 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { Layout.fillWidth: true; text: playerTitle; color: themeColors.text; font.pixelSize: 12; font.weight: Font.Bold; elide: Text.ElideRight }
                            Text { Layout.fillWidth: true; text: playerArtist; color: themeColors.muted; font.pixelSize: 10; elide: Text.ElideRight }
                        }
                        Rectangle {
                            Layout.preferredWidth: 28; Layout.preferredHeight: 28
                            radius: 14; color: themeColors.lime
                            Icon { anchors.centerIn: parent; name: playerPlaying ? "pause" : "play"; color: "#14190b"; implicitWidth: 13; implicitHeight: 13 }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: bridge.togglePlayback() }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: themeColors.border }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: 12; Layout.bottomMargin: 12
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Downloads folder"; color: themeColors.muted; font.pixelSize: 10; font.weight: Font.Medium }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: "Change folder"; font.pixelSize: 10; font.weight: Font.DemiBold
                            color: changeMouse.containsMouse ? themeColors.lime : themeColors.muted
                            MouseArea { id: changeMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.chooseOutputFolder() }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        radius: 9
                        color: themeColors.panel
                        border.color: folderMouse.containsMouse ? themeColors.borderHi : themeColors.border
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            spacing: 8
                            Icon { name: "folder"; color: themeColors.muted; implicitWidth: 13; implicitHeight: 13 }
                            Text {
                                Layout.fillWidth: true
                                text: settingsData.output_dir || ""
                                color: themeColors.muted; font.pixelSize: 9; font.family: "monospace"
                                elide: Text.ElideMiddle
                            }
                        }
                        MouseArea { id: folderMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.openOutputFolder() }
                    }
                }
            }
        }

        StackView {
            id: pageStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            pushEnter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 230; easing.type: Easing.OutCubic }
                NumberAnimation { property: "x"; from: 24; to: 0; duration: 280; easing.type: Easing.OutCubic } } }
            pushExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 140 } }
            replaceEnter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
                NumberAnimation { property: "x"; from: 18; to: 0; duration: 260; easing.type: Easing.OutCubic } } }
            replaceExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }
        }
    }

    // ── Player bar ────────────────────────────────────────────────
    Rectangle {
        id: playerDock
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: hasTrack ? 62 : 0
        visible: height > 0
        clip: true
        color: themeColors.bg
        Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 1; color: themeColors.border }

        RowLayout {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.min(parent.width - 40, 1130)
            spacing: 16

            // Track
            RowLayout {
                Layout.preferredWidth: 215
                Layout.maximumWidth: 215
                spacing: 11
                Rectangle {
                    Layout.preferredWidth: 42; Layout.preferredHeight: 42
                    radius: 8; color: themeColors.panel2; clip: true
                    Image { anchors.fill: parent; source: selectedTrack.cover || ""; sourceSize.width: 96; sourceSize.height: 96; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                    Icon { anchors.centerIn: parent; name: "music"; color: themeColors.lime; visible: !selectedTrack.cover; implicitWidth: 18; implicitHeight: 18 }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text { Layout.fillWidth: true; text: playerTitle; color: themeColors.text; font.pixelSize: 12; font.weight: Font.Bold; elide: Text.ElideRight }
                    Text { Layout.fillWidth: true; text: playerArtist; color: themeColors.subtle; font.pixelSize: 10; elide: Text.ElideRight }
                }
            }

            // Transport
            RowLayout {
                spacing: 4
                BarButton { icon: "shuffle"; active: playerShuffle; onClicked: bridge.toggleShuffle() }
                BarButton { icon: "previous"; enabled: playerCanSkip; onClicked: bridge.playPrevious() }
                Rectangle {
                    Layout.preferredWidth: 36; Layout.preferredHeight: 36
                    Layout.leftMargin: 4; Layout.rightMargin: 4
                    radius: 18
                    color: themeColors.lime
                    scale: playMouse.pressed ? 0.94 : playMouse.containsMouse ? 1.05 : 1
                    Behavior on scale { NumberAnimation { duration: 110 } }
                    Icon { anchors.centerIn: parent; anchors.horizontalCenterOffset: playerPlaying ? 0 : 1; name: playerPlaying ? "pause" : "play"; color: "#14190b"; implicitWidth: 15; implicitHeight: 15 }
                    MouseArea { id: playMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.togglePlayback() }
                }
                BarButton { icon: "next"; enabled: playerCanSkip; onClicked: bridge.playNext() }
                BarButton { icon: playerRepeat === 2 ? "repeat-1" : "repeat"; active: playerRepeat > 0; onClicked: bridge.cycleRepeat() }
            }

            // Seek
            RowLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 160
                spacing: 9
                Text { text: formatDuration(playerPosition / 1000); color: themeColors.subtle; font.pixelSize: 10; font.family: "monospace"; Layout.preferredWidth: 34; horizontalAlignment: Text.AlignRight }
                Slider {
                    id: playerSeek
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    from: 0; to: Math.max(1, playerDuration); value: playerPosition
                    enabled: playerDuration > 0
                    onMoved: bridge.seekPlayer(value)
                    background: Rectangle {
                        x: playerSeek.leftPadding
                        y: playerSeek.topPadding + playerSeek.availableHeight / 2 - height / 2
                        width: playerSeek.availableWidth; height: 4; radius: 2; color: themeColors.panel3
                        Rectangle { width: parent.width * playerSeek.visualPosition; height: parent.height; radius: 2; color: themeColors.lime }
                    }
                    handle: Rectangle {
                        x: playerSeek.leftPadding + playerSeek.visualPosition * (playerSeek.availableWidth - width)
                        y: playerSeek.topPadding + playerSeek.availableHeight / 2 - height / 2
                        width: 11; height: 11; radius: 6; color: themeColors.lime
                    }
                }
                Text { text: formatDuration(playerDuration / 1000); color: themeColors.subtle; font.pixelSize: 10; font.family: "monospace"; Layout.preferredWidth: 34 }
            }

            // Volume
            RowLayout {
                spacing: 4
                BarButton { icon: playerMuted || playerVolume <= 0 ? "volume-x" : playerVolume < 0.45 ? "volume-1" : "volume"; onClicked: bridge.toggleMute() }
                Slider {
                    id: playerVolumeSlider
                    Layout.preferredWidth: 84
                    Layout.preferredHeight: 28
                    from: 0; to: 1; value: playerVolume
                    onMoved: bridge.setVolume(value)
                    background: Rectangle {
                        x: playerVolumeSlider.leftPadding
                        y: playerVolumeSlider.topPadding + playerVolumeSlider.availableHeight / 2 - height / 2
                        width: playerVolumeSlider.availableWidth; height: 4; radius: 2; color: themeColors.panel3
                        Rectangle { width: parent.width * playerVolumeSlider.visualPosition; height: parent.height; radius: 2; color: themeColors.text }
                    }
                    handle: Rectangle {
                        x: playerVolumeSlider.leftPadding + playerVolumeSlider.visualPosition * (playerVolumeSlider.availableWidth - width)
                        y: playerVolumeSlider.topPadding + playerVolumeSlider.availableHeight / 2 - height / 2
                        width: 11; height: 11; radius: 6; color: themeColors.text
                    }
                }
            }

            // Actions
            RowLayout {
                spacing: 2
                BarButton { icon: "download"; visible: playerPath.indexOf("http") === 0; onClicked: bridge.enqueueMusicResult(playerTitle, playerArtist, selectedTrack.cover || "") }
                BarButton { icon: "heart"; visible: playerPath.length > 0 && playerPath.indexOf("http") !== 0; onClicked: bridge.addFileToPlaylist("Favorites", playerPath) }
                BarButton { icon: "queue"; onClicked: setPage("Downloads") }
                BarButton { icon: "playlist"; onClicked: setPage("Playlists") }
                BarButton { icon: "lyrics"; onClicked: bridge.findCurrentLyrics() }
                BarButton { icon: "close"; onClicked: bridge.closePlayer() }
            }
        }
    }

    Component {
        id: discoverPage
        Flickable {
            id: discoverFlick
            clip: true
            contentWidth: width
            contentHeight: discoverColumn.implicitHeight + 70
            ScrollBar.vertical: ScrollBar { active: true }
            readonly property bool idleState: searchQuery.length === 0 && searchItems.length === 0 && !searchBusy && detailData === null
            ColumnLayout {
                id: discoverColumn
                width: Math.min(parent.width - 100, 992)
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 22
                Item { Layout.preferredHeight: 14 }

                // Search bar
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    radius: 14
                    color: themeColors.panel
                    border.color: catalogInput.activeFocus ? themeColors.borderHi : themeColors.border
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16; anchors.rightMargin: 9
                        spacing: 10
                        Icon { name: "search"; color: themeColors.lime; implicitWidth: 17; implicitHeight: 17 }
                        TextField {
                            id: catalogInput
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: searchQuery
                            placeholderText: "Search for a track, album or artist — or paste a Spotify link"
                            placeholderTextColor: themeColors.subtle
                            color: themeColors.text
                            selectionColor: themeColors.lime
                            selectedTextColor: "#14190b"
                            background: null
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                            leftPadding: 0
                            verticalAlignment: TextInput.AlignVCenter
                            function submit(value) {
                                var t = (value !== undefined ? value : text).trim()
                                if (!t.length) return
                                window.runSearch(t, providerBox.currentText)
                            }
                            onAccepted: submit()
                        }
                        ComboBox { id: providerBox; visible: false; model: ["All catalogs","Deezer","Apple Music","YouTube","SoundCloud"] }
                        Rectangle {
                            Layout.preferredHeight: 40
                            Layout.preferredWidth: searchBtnRow.implicitWidth + 34
                            radius: 10
                            color: themeColors.lime
                            opacity: searchBusy ? 0.6 : (catalogInput.text.trim().length ? 1 : 0.55)
                            Behavior on opacity { NumberAnimation { duration: 140 } }
                            RowLayout {
                                id: searchBtnRow
                                anchors.centerIn: parent
                                spacing: 7
                                Text { text: searchBusy ? "Searching…" : "Search"; color: "#14190b"; font.pixelSize: 13; font.weight: Font.Bold }
                                Icon { visible: !searchBusy; name: "arrow-right"; color: "#14190b"; implicitWidth: 14; implicitHeight: 14; strokeWidth: 2.4 }
                            }
                            MouseArea { anchors.fill: parent; enabled: !searchBusy; cursorShape: Qt.PointingHandCursor; onClicked: catalogInput.submit() }
                        }
                    }
                }

                // Idle: provider chips + recent searches
                Flow {
                    visible: discoverFlick.idleState
                    Layout.fillWidth: true
                    spacing: 8
                    Repeater {
                        model: [
                            {label: "Spotify", idx: -1}, {label: "YouTube Music", idx: 3}, {label: "SoundCloud", idx: 4},
                            {label: "Deezer", idx: 1}, {label: "Apple Music", idx: 2}
                        ]
                        delegate: Rectangle {
                            readonly property bool on: modelData.idx >= 0 && providerBox.currentIndex === modelData.idx
                            width: chipRow.implicitWidth + 26; height: 28; radius: 14
                            color: on ? themeColors.activeBg : themeColors.panel
                            border.color: on ? themeColors.borderHi : themeColors.border
                            RowLayout {
                                id: chipRow
                                anchors.centerIn: parent
                                spacing: 7
                                Rectangle { width: 6; height: 6; radius: 3; color: themeColors.lime }
                                Text { text: modelData.label; color: on ? themeColors.lime : themeColors.muted; font.pixelSize: 11; font.weight: Font.DemiBold }
                            }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (modelData.idx < 0) { toast.showMessage("Paste a Spotify track, album or playlist link into the search box."); return }
                                    providerBox.currentIndex = providerBox.currentIndex === modelData.idx ? 0 : modelData.idx
                                }
                            }
                        }
                    }
                }
                ColumnLayout {
                    visible: discoverFlick.idleState && recentSearches.length > 0
                    Layout.fillWidth: true
                    spacing: 12
                    RowLayout {
                        spacing: 8
                        Text { text: "Recent searches"; color: themeColors.muted; font.pixelSize: 11; font.weight: Font.DemiBold }
                        Icon {
                            name: "close"; color: clearMouse.containsMouse ? themeColors.text : themeColors.subtle; implicitWidth: 12; implicitHeight: 12
                            MouseArea { id: clearMouse; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.setRecentSearches("[]") }
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 10
                        Repeater {
                            model: recentSearches
                            delegate: Rectangle {
                                height: 36; radius: 18
                                width: Math.min(recentRow.implicitWidth + 30, 300)
                                color: recentMouse.containsMouse ? themeColors.panel2 : themeColors.panel
                                border.color: themeColors.border
                                RowLayout {
                                    id: recentRow
                                    anchors.centerIn: parent
                                    width: Math.min(implicitWidth, 270)
                                    spacing: 8
                                    Icon { name: modelData.indexOf("http") === 0 ? "link" : "search"; color: themeColors.subtle; implicitWidth: 13; implicitHeight: 13 }
                                    Text { Layout.fillWidth: true; text: modelData; color: themeColors.text; font.pixelSize: 12; font.weight: Font.Medium; elide: Text.ElideRight }
                                }
                                MouseArea { id: recentMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: catalogInput.submit(modelData) }
                            }
                        }
                    }
                }

                // ── Detail view (track / album / playlist / artist) ──
                ColumnLayout {
                    visible: detailData !== null
                    Layout.fillWidth: true
                    spacing: 18
                    Item {
                        Layout.preferredHeight: 26
                        Layout.preferredWidth: backRow.implicitWidth + 16
                        RowLayout {
                            id: backRow
                            anchors.verticalCenter: parent.verticalCenter
                            x: 8
                            spacing: 8
                            Icon { name: "arrow-left"; color: backMouse.containsMouse ? themeColors.text : themeColors.muted; implicitWidth: 14; implicitHeight: 14 }
                            Text { text: "Back to results"; color: backMouse.containsMouse ? themeColors.text : themeColors.muted; font.pixelSize: 12; font.weight: Font.Medium }
                        }
                        MouseArea { id: backMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { detailData = null; detailLoading = false } }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        radius: 16
                        color: themeColors.panel
                        border.color: themeColors.border
                        implicitHeight: detailCol.implicitHeight
                        ColumnLayout {
                            id: detailCol
                            width: parent.width
                            spacing: 0
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.margins: 24
                                spacing: 22
                                CoverBox { source: detailData ? detailData.cover : ""; box: 96; corner: 8 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Text { text: detailData ? window.kindLabel(detailData.kind) : ""; color: themeColors.lime; font.pixelSize: 11; font.weight: Font.Bold }
                                    Text { Layout.fillWidth: true; text: detailData ? detailData.title : ""; color: themeColors.text; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.5; elide: Text.ElideRight }
                                    Text { Layout.fillWidth: true; text: window.detailMeta(); color: themeColors.muted; font.pixelSize: 13; elide: Text.ElideRight }
                                }
                                RowLayout {
                                    spacing: 8
                                    Rectangle {
                                        Layout.preferredWidth: 40; Layout.preferredHeight: 40
                                        radius: 10; color: detailPlayMouse.containsMouse ? themeColors.limeSoft : themeColors.lime
                                        opacity: detailData && detailData.tracks.length ? 1 : 0.5
                                        Icon { anchors.centerIn: parent; anchors.horizontalCenterOffset: 1; name: "play"; color: "#14190b"; implicitWidth: 16; implicitHeight: 16 }
                                        MouseArea { id: detailPlayMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: window.playDetail(0) }
                                    }
                                    SquareButton { Layout.preferredWidth: 40; Layout.preferredHeight: 40; radius: 10; icon: "link"; glyph: 16; onClicked: bridge.openCatalogUrl(detailData ? detailData.url : "") }
                                    Btn { text: "Download all"; icon: "download"; primary: true; implicitHeight: 40; enabled: detailData !== null && detailData.tracks.length > 0; onClicked: window.downloadDetail() }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: themeColors.border }
                            Text {
                                visible: detailLoading
                                Layout.fillWidth: true; Layout.margins: 30
                                horizontalAlignment: Text.AlignHCenter
                                text: "Loading tracks…"; color: themeColors.muted; font.pixelSize: 12
                            }
                            Text {
                                visible: !detailLoading && detailData !== null && detailData.tracks.length === 0
                                Layout.fillWidth: true; Layout.margins: 30
                                horizontalAlignment: Text.AlignHCenter
                                text: "No tracks were found for this item."; color: themeColors.muted; font.pixelSize: 12
                            }
                            Repeater {
                                model: detailData ? detailData.tracks : []
                                delegate: Item {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 62
                                    Rectangle { anchors.fill: parent; color: detailRowMouse.containsMouse ? themeColors.panel2 : "transparent" }
                                    MouseArea { id: detailRowMouse; anchors.fill: parent; hoverEnabled: true; onDoubleClicked: window.playDetail(index) }
                                    Rectangle { visible: index > 0; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 20; anchors.rightMargin: 20; height: 1; color: themeColors.border; opacity: 0.5 }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 20; anchors.rightMargin: 20
                                        spacing: 14
                                        Text { Layout.preferredWidth: 22; text: index + 1; color: themeColors.subtle; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter }
                                        CoverBox { source: modelData.cover || ""; box: 40; corner: 6 }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Text { Layout.fillWidth: true; text: modelData.title; color: themeColors.text; font.pixelSize: 13; font.weight: Font.Bold; elide: Text.ElideRight }
                                            Text { Layout.fillWidth: true; text: modelData.artist; color: themeColors.muted; font.pixelSize: 12; elide: Text.ElideRight }
                                        }
                                        SquareButton { icon: "lyrics"; onClicked: bridge.findLyrics(modelData.title, modelData.artist) }
                                        SquareButton { icon: "play"; onClicked: window.playDetail(index) }
                                        Text { Layout.preferredWidth: 40; text: formatDuration(modelData.duration); color: themeColors.muted; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                                        SquareButton { icon: "download"; accent: true; onClicked: { bridge.enqueueMusicResult(modelData.title, modelData.artist, modelData.cover || ""); toast.showMessage("Added to downloads.") } }
                                    }
                                }
                            }
                        }
                    }
                }

                // ── Results ──
                Rectangle {
                    visible: !discoverFlick.idleState && detailData === null
                    Layout.fillWidth: true
                    radius: 16
                    color: themeColors.panel
                    border.color: themeColors.border
                    implicitHeight: resultsCol.implicitHeight
                    ColumnLayout {
                        id: resultsCol
                        width: parent.width
                        spacing: 0
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.margins: 20
                            Layout.bottomMargin: 16
                            spacing: 14
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: "Results for"; color: themeColors.text; font.pixelSize: 16; font.weight: Font.Bold }
                                Text { Layout.maximumWidth: 420; text: searchQuery; color: themeColors.lime; font.pixelSize: 16; font.weight: Font.Bold; elide: Text.ElideRight }
                                Item { Layout.fillWidth: true }
                                Text { text: searchItems.length + (searchBusy ? " results so far" : " results"); color: themeColors.muted; font.pixelSize: 12; font.weight: Font.Medium }
                            }
                            Row {
                                spacing: 6
                                Repeater {
                                    model: ["All", "Tracks", "Artists", "Albums", "Playlists"]
                                    delegate: Rectangle {
                                        readonly property bool on: searchTab === modelData
                                        readonly property int n: modelData === "All" ? searchItems.length : window.searchCount(modelData)
                                        height: 32; radius: 16
                                        width: tabRow.implicitWidth + 28
                                        color: on ? themeColors.lime : (tabMouse.containsMouse ? themeColors.panel2 : "transparent")
                                        RowLayout {
                                            id: tabRow
                                            anchors.centerIn: parent
                                            spacing: 6
                                            Text { text: modelData; color: on ? "#14190b" : themeColors.text; font.pixelSize: 12; font.weight: Font.DemiBold }
                                            Text { text: n; color: on ? "#14190b" : themeColors.subtle; font.pixelSize: 11; opacity: on ? 0.75 : 1 }
                                        }
                                        MouseArea { id: tabMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: searchTab = modelData }
                                    }
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: themeColors.border }
                        Repeater {
                            model: visibleSearchRows
                            delegate: Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: modelData.header ? 40 : 61
                                // section header
                                RowLayout {
                                    visible: modelData.header
                                    anchors.fill: parent
                                    anchors.leftMargin: 20; anchors.topMargin: 6
                                    spacing: 8
                                    Icon { name: window.kindIcon(modelData.kind); color: themeColors.muted; implicitWidth: 13; implicitHeight: 13 }
                                    Text { text: modelData.kind || ""; color: themeColors.muted; font.pixelSize: 11; font.weight: Font.DemiBold }
                                }
                                // result row
                                Item {
                                    visible: !modelData.header
                                    anchors.fill: parent
                                    Rectangle { anchors.fill: parent; color: rowMouse.containsMouse ? themeColors.panel2 : "transparent" }
                                    MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: window.openResult(modelData.row) }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 20; anchors.rightMargin: 20
                                        spacing: 14
                                        CoverBox { source: modelData.row ? (modelData.row.cover || "") : ""; box: 42; corner: 6 }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Text { Layout.fillWidth: true; text: modelData.row ? modelData.row.title : ""; color: themeColors.text; font.pixelSize: 13; font.weight: Font.Bold; elide: Text.ElideRight }
                                            Text {
                                                Layout.fillWidth: true
                                                text: modelData.row ? ([modelData.row.artist, (modelData.row.kind || "Tracks") !== "Tracks" ? modelData.row.album : ""].filter(function(v) { return v }).join(" · ")) : ""
                                                color: themeColors.muted; font.pixelSize: 12; elide: Text.ElideRight
                                            }
                                        }
                                        ProviderChip { provider: modelData.row ? modelData.row.provider : "" }
                                        SquareButton {
                                            visible: !!modelData.row && (modelData.row.kind || "Tracks") === "Tracks"
                                            icon: "download"
                                            onClicked: { bridge.enqueueMusicResult(modelData.row.title, modelData.row.artist, modelData.row.cover || ""); toast.showMessage("Added to downloads.") }
                                        }
                                        Icon { visible: !!modelData.row && (modelData.row.kind || "Tracks") !== "Tracks"; name: "chevron-right"; color: themeColors.subtle; implicitWidth: 16; implicitHeight: 16; Layout.rightMargin: 8 }
                                    }
                                }
                            }
                        }
                        Text {
                            visible: visibleSearchRows.length === 0
                            Layout.fillWidth: true
                            Layout.margins: 40
                            horizontalAlignment: Text.AlignHCenter
                            text: searchBusy ? "Searching catalogs…" : "No results. Try another search."
                            color: themeColors.subtle; font.pixelSize: 12
                        }
                        Item { Layout.preferredHeight: 8 }
                    }
                }
                Item { Layout.preferredHeight: 20 }
            }
        }
    }

    Component {
        id: downloaderPage
        Flickable {
            clip: true
            contentWidth: width
            contentHeight: downloaderColumn.implicitHeight + 56
            ScrollBar.vertical: ScrollBar { active: true }
            ColumnLayout {
                id: downloaderColumn
                width: Math.min(parent.width - 100, 1040)
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 18
                Item { Layout.preferredHeight: 12 }
                Text { text: "MEDIA DOWNLOADER"; color: themeColors.lime; font.pixelSize: 9; font.letterSpacing: 1.5 }
                Text { text: "Download anything you can access."; color: themeColors.text; font.pixelSize: 32; font.weight: Font.Bold }
                Text { text: "Paste a video, audio, or playlist URL from YouTube and other yt-dlp-supported sites. Spotify links use the credential-free music matcher."; color: themeColors.muted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Rectangle {
                    Layout.fillWidth: true; radius: 13; color: themeColors.panel; border.color: themeColors.border
                    implicitHeight: 250
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 18; spacing: 12
                        RowLayout {
                            Text { text: "SOURCE LINKS"; color: themeColors.lime; font.pixelSize: 9; font.letterSpacing: 1.2 }
                            Item { Layout.fillWidth: true }
                            Text { text: "One URL per line"; color: themeColors.subtle; font.pixelSize: 9 }
                        }
                        TextArea {
                            id: downloadUrls
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
                            Layout.fillWidth: true; Layout.fillHeight: true
                            placeholderText: "Paste a YouTube, Vimeo, SoundCloud, or other supported URL…\nAdd multiple links on separate lines."
                            color: themeColors.text; placeholderTextColor: themeColors.subtle
                            wrapMode: TextEdit.Wrap
                            background: Rectangle { radius: 8; color: themeColors.panel2; border.color: themeColors.border }
                            font.pixelSize: 11
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            Button {
                                text: window.analysisBusy ? "Analyzing…" : "Analyze URL"
                                enabled: !window.analysisBusy
                                onClicked: {
                                    var urls = downloadUrls.text.split(/\r?\n/).map(function(v){return v.trim()}).filter(function(v){return v.length})
                                    if (!urls.length) {
                                        toast.showMessage("Paste a media URL first.", true)
                                        return
                                    }
                                    if (!/^https?:\/\/[^\/\s?#]+(?:[\/?#]|$)/i.test(urls[0])) {
                                        toast.showMessage("Enter a complete http:// or https:// media URL.", true)
                                        return
                                    }
                                    window.analysisTargetUrl = urls[0]
                                    window.analysisBusy = true
                                    window.analysisError = ""
                                    window.analysisData = ({})
                                    window.analysisThumbnailList = []
                                    window.analysisThumbnailIndex = 0
                                    analysisDialog.open()
                                    bridge.analyzeUrl(urls[0], "download")
                                }
                                background: Rectangle { radius: 8; color: parent.enabled ? themeColors.panel2 : themeColors.panel3; border.color: parent.enabled ? themeColors.border : "transparent" }
                                contentItem: Text { text: parent.text; color: parent.enabled ? themeColors.text : themeColors.subtle; font.pixelSize: 10; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; padding: 8 }
                            }
                            Item { Layout.fillWidth: true }
                            Button {
                                text: "Add URLs to queue"
                                onClicked: {
                                    var urls = downloadUrls.text.split(/\r?\n/).map(function(v){return v.trim()}).filter(function(v){return v.length})
                                    if (!urls.length) { toast.showMessage("Paste one or more media URLs first.", true); return }
                                    var optionsJson = JSON.stringify(advancedDownloadPanel.options())
                                    for (var i = 0; i < urls.length; i++) {
                                        if (/open\.spotify\.com\/(track|album|playlist)\//i.test(urls[i]))
                                            bridge.enqueueSpotify(urls[i])
                                        else
                                            bridge.enqueueDownloadWithOptions(urls[i], optionsJson)
                                    }
                                    toast.showMessage("Added " + urls.length + " URL(s) to the queue.")
                                    downloadUrls.text = ""
                                    setPage("Downloads")
                                }
                                background: Rectangle { radius: 8; color: themeColors.lime }
                                contentItem: Text { text: parent.text; color: "#14190b"; font.pixelSize: 10; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; padding: 9 }
                            }
                        }
                    }
                }
                AdvancedDownloadPanel {
                    id: advancedDownloadPanel
                    Layout.fillWidth: true
                    palette: window.themeColors
                    presets: window.presets
                    selectedPreset: window.presetName
                    onPresetChanged: function(name) { window.presetName = name }
                    onSavePresetRequested: function(optionsJson) {
                        var savedName = bridge.saveCustomPreset(optionsJson)
                        if (savedName)
                            window.presetName = savedName
                    }
                }
            }
        }
    }

    Component {
        id: downloadsPage
        Item {
            Rectangle {
                id: dlHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 90
                color: "transparent"
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: themeColors.border }
                RowLayout {
                    width: Math.min(parent.width - 100, 1088)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12
                    ColumnLayout {
                        spacing: 4
                        Text { text: "Downloads"; color: themeColors.text; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.6 }
                        Text { text: downloadCounts.done + " finished"; color: themeColors.muted; font.pixelSize: 12 }
                    }
                    Item { Layout.fillWidth: true }
                    Btn { text: "Clear finished"; icon: "trash"; implicitHeight: 34; visible: downloadCounts.done > 0; onClicked: bridge.clearFinished() }
                    Rectangle {
                        Layout.preferredHeight: 38
                        Layout.preferredWidth: dlTabs.implicitWidth + 10
                        radius: 12; color: "transparent"; border.color: themeColors.border
                        Row {
                            id: dlTabs
                            anchors.centerIn: parent
                            spacing: 2
                            Repeater {
                                model: [
                                    {label: "All", key: "All", n: downloadCounts.all},
                                    {label: "Downloading", key: "Downloading", n: downloadCounts.active},
                                    {label: "Completed", key: "Completed", n: downloadCounts.done}
                                ]
                                delegate: Rectangle {
                                    readonly property bool on: downloadTab === modelData.key
                                    height: 30; radius: 9
                                    width: dlTabRow.implicitWidth + 24
                                    color: on ? themeColors.panel3 : "transparent"
                                    RowLayout {
                                        id: dlTabRow
                                        anchors.centerIn: parent
                                        spacing: 7
                                        Text { text: modelData.label; color: on ? themeColors.text : themeColors.muted; font.pixelSize: 12; font.weight: on ? Font.Bold : Font.Medium }
                                        Rectangle {
                                            visible: true
                                            width: Math.max(18, dlTabCount.implicitWidth + 10); height: 18; radius: 9
                                            color: on ? themeColors.activeBg : "transparent"
                                            Text { id: dlTabCount; anchors.centerIn: parent; text: modelData.n; color: on ? themeColors.lime : themeColors.subtle; font.pixelSize: 10; font.weight: Font.Bold }
                                        }
                                    }
                                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: downloadTab = modelData.key }
                                }
                            }
                        }
                    }
                }
            }
            Flickable {
                anchors.top: dlHeader.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                clip: true
                contentWidth: width
                contentHeight: dlCol.implicitHeight + 40
                ScrollBar.vertical: ScrollBar { active: true }
                ColumnLayout {
                    id: dlCol
                    width: Math.min(parent.width - 100, 1088)
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 16
                    Item { Layout.preferredHeight: 4 }
                    EmptyState {
                        visible: downloadGroupsModel.count === 0
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: 90
                        icon: "download"
                        title: downloadTab === "All" ? "No downloads yet" : (downloadTab === "Downloading" ? "No active downloads" : "Nothing completed yet")
                        body: "Search for a track, album, or artist to start building your offline music library."
                    }
                    Btn {
                        visible: downloadGroupsModel.count === 0
                        Layout.alignment: Qt.AlignHCenter
                        text: "Search & Explore"; icon: "search"; primary: true
                        onClicked: setPage("Discover")
                    }
                    Repeater {
                        model: downloadGroupsModel
                        delegate: Rectangle {
                            id: groupCard
                            Layout.fillWidth: true
                            radius: 14
                            color: themeColors.panel
                            border.color: themeColors.border
                            implicitHeight: groupCol.implicitHeight
                            clip: true
                            property string rj: rowsJson
                            ListModel { id: rowsModel }
                            onRjChanged: window.syncListModel(rowsModel, JSON.parse(rj))
                            Component.onCompleted: window.syncListModel(rowsModel, JSON.parse(rj))
                            ColumnLayout {
                                id: groupCol
                                width: parent.width
                                spacing: 0
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.margins: 14
                                    spacing: 14
                                    CoverBox { source: cover; box: 50; corner: 8 }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 5
                                        Text { Layout.fillWidth: true; text: name; color: themeColors.text; font.pixelSize: 14; font.weight: Font.Bold; elide: Text.ElideRight }
                                        Text {
                                            visible: uploader.length > 0 || duration > 0
                                            text: uploader + (duration > 0 ? (uploader.length > 0 ? " · " : "") + window.formatMediaDuration(duration) : "")
                                            color: themeColors.subtle; font.pixelSize: 11
                                            elide: Text.ElideRight; Layout.fillWidth: true
                                        }
                                        RowLayout {
                                            spacing: 7
                                            Icon { name: active > 0 ? "download" : (failed > 0 && done === 0 ? "alert" : "check"); color: active > 0 ? themeColors.lime : (failed > 0 && done === 0 ? themeColors.danger : themeColors.lime); implicitWidth: 13; implicitHeight: 13 }
                                            Text {
                                                text: active > 0 ? ("Downloading · " + (done + failed) + " of " + total + " · " + pct + "%")
                                                               : (done + " of " + total + " downloaded")
                                                color: themeColors.lime; font.pixelSize: 12; font.weight: Font.DemiBold
                                            }
                                            Text { visible: failed > 0; text: "· " + failed + " failed"; color: themeColors.danger; font.pixelSize: 12; font.weight: Font.DemiBold }
                                            Text { visible: cancelled > 0; text: "· " + cancelled + " cancelled"; color: themeColors.subtle; font.pixelSize: 12 }
                                        }
                                    }
                                    Btn {
                                        visible: failed > 0 || cancelled > 0
                                        text: "Retry"; icon: "refresh"; danger: true; implicitHeight: 34
                                        onClicked: { if (grouped) bridge.retryGroup(gid); else if (rowsModel.count) bridge.retryTask(rowsModel.get(0).tid) }
                                    }
                                    Btn {
                                        visible: active > 0
                                        text: "Cancel"; implicitHeight: 34
                                        onClicked: { for (var i = 0; i < rowsModel.count; i++) { var r = rowsModel.get(i); if (r.status === "Queued" || r.status === "Starting" || r.status === "Running") bridge.cancelTask(r.tid) } }
                                    }
                                    Rectangle {
                                        visible: active === 0
                                        Layout.preferredWidth: 32; Layout.preferredHeight: 32
                                        radius: 8; color: trashMouse.containsMouse ? themeColors.panel2 : "transparent"
                                        Icon { anchors.centerIn: parent; name: "trash"; color: trashMouse.containsMouse ? themeColors.danger : themeColors.subtle; implicitWidth: 15; implicitHeight: 15 }
                                        MouseArea { id: trashMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.removeGroup(grouped ? gid : (rowsModel.count ? rowsModel.get(0).tid : gid)) }
                                    }
                                }
                                Rectangle {
                                    visible: active > 0
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 3
                                    color: themeColors.panel3
                                    Rectangle { width: parent.width * (pct / 100); height: parent.height; color: themeColors.lime; Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } } }
                                }
                                Rectangle {
                                    visible: failed > 0 && errorText.length > 0
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 48
                                    color: "#241311"
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 16; anchors.rightMargin: 12
                                        spacing: 10
                                        Icon { name: "alert"; color: themeColors.danger; implicitWidth: 14; implicitHeight: 14 }
                                        Text {
                                            Layout.fillWidth: true
                                            text: signIn ? "YouTube wants a sign-in for this one — set Browser cookies in Settings." : errorText
                                            color: themeColors.danger; font.pixelSize: 12; elide: Text.ElideRight
                                        }
                                        Btn { visible: signIn; text: "Fix in Settings"; icon: "sliders"; implicitHeight: 30; onClicked: setPage("Settings") }
                                    }
                                }
                                ListView {
                                    id: trackList
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.min(rowsModel.count * 36, 252)
                                    clip: true
                                    model: rowsModel
                                    interactive: contentHeight > height
                                    boundsBehavior: Flickable.StopAtBounds
                                    ScrollBar.vertical: ScrollBar { active: true; policy: trackList.contentHeight > trackList.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                                    delegate: Item {
                                        width: trackList.width
                                        height: 36
                                        Rectangle { anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 16; anchors.rightMargin: 16; height: 1; color: themeColors.border; opacity: 0.5 }
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 18; anchors.rightMargin: 24
                                            spacing: 12
                                            Icon {
                                                name: status === "Completed" ? "check" : (status === "Failed" ? "x" : (status === "Cancelled" ? "x" : ((status === "Running" || status === "Starting") ? "download" : "clock")))
                                                color: status === "Completed" ? themeColors.lime : (status === "Failed" ? themeColors.danger : ((status === "Running" || status === "Starting") ? themeColors.lime : themeColors.subtle))
                                                implicitWidth: 13; implicitHeight: 13
                                            }
                                            Text { Layout.fillWidth: true; text: title + (artist.length ? "  ·  " + artist : ""); color: themeColors.text; font.pixelSize: 12; font.weight: Font.Medium; elide: Text.ElideRight }
                                            Text { visible: status === "Running" || status === "Starting"; text: progress + "%"; color: themeColors.lime; font.pixelSize: 11; font.weight: Font.DemiBold }
                                            Text { visible: status === "Failed"; Layout.maximumWidth: 260; text: detail; color: themeColors.danger; font.pixelSize: 10; elide: Text.ElideRight }
                                            Row {
                                                visible: status === "Completed" && folder.length > 0
                                                spacing: 6
                                                Icon { name: "folder"; color: openMouse.containsMouse ? themeColors.text : themeColors.subtle; implicitWidth: 13; implicitHeight: 13 }
                                                Text { text: "Open Folder"; color: openMouse.containsMouse ? themeColors.text : themeColors.subtle; font.pixelSize: 11; font.weight: Font.Medium
                                                    MouseArea { id: openMouse; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.openPath(folder) } }
                                            }
                                            Icon {
                                                visible: status === "Queued" || status === "Starting" || status === "Running"
                                                name: "close"; color: itemCancelMouse.containsMouse ? themeColors.text : themeColors.subtle; implicitWidth: 12; implicitHeight: 12
                                                MouseArea { id: itemCancelMouse; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.cancelTask(tid) }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 20 }
                }
            }
        }
    }

    Component {
        id: libraryPage
        Flickable {
            clip: true
            contentWidth: width
            contentHeight: libraryColumn.implicitHeight + 50
            ScrollBar.vertical: ScrollBar { active: true }
            ColumnLayout {
                id: libraryColumn
                width: Math.min(parent.width - 96, 1030)
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 16
                Item { Layout.preferredHeight: 14 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    ColumnLayout {
                        spacing: 3
                        RowLayout {
                            spacing: 10
                            Text { text: "Library"; color: themeColors.text; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.6 }
                            Rectangle {
                                width: countText.implicitWidth + 18; height: 22; radius: 11
                                color: themeColors.activeBg; border.color: themeColors.borderHi
                                Text { id: countText; anchors.centerIn: parent; text: libraryItems.length + " songs"; color: themeColors.lime; font.pixelSize: 10; font.weight: Font.Bold }
                            }
                        }
                        Text { text: "Offline Music Library"; color: themeColors.muted; font.pixelSize: 12 }
                    }
                    Item { Layout.fillWidth: true }
                    Rectangle {
                        Layout.preferredHeight: 36
                        Layout.preferredWidth: playAllRow.implicitWidth + 30
                        radius: 10; color: themeColors.lime
                        scale: playAllMouse.pressed ? 0.97 : 1
                        Behavior on scale { NumberAnimation { duration: 100 } }
                        RowLayout {
                            id: playAllRow
                            anchors.centerIn: parent
                            spacing: 7
                            Icon { name: "play"; color: "#14190b"; implicitWidth: 13; implicitHeight: 13 }
                            Text { text: "Play all"; color: "#14190b"; font.pixelSize: 12; font.weight: Font.Bold }
                        }
                        MouseArea { id: playAllMouse; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: bridge.playAllLibrary() }
                    }
                    Rectangle {
                        Layout.preferredWidth: 36; Layout.preferredHeight: 36
                        radius: 10; color: shuffleAllMouse.containsMouse ? themeColors.panel2 : themeColors.panel; border.color: themeColors.border
                        Icon { anchors.centerIn: parent; name: "shuffle"; color: themeColors.text; implicitWidth: 15; implicitHeight: 15 }
                        MouseArea { id: shuffleAllMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.shuffleLibrary() }
                    }
                    Rectangle {
                        Layout.preferredWidth: 210; Layout.preferredHeight: 36
                        radius: 10; color: themeColors.panel
                        border.color: libraryFilterInput.activeFocus ? themeColors.borderHi : themeColors.border
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 11; anchors.rightMargin: 8
                            spacing: 8
                            Icon { name: "search"; color: themeColors.muted; implicitWidth: 14; implicitHeight: 14 }
                            TextField {
                                id: libraryFilterInput
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
                                Layout.fillWidth: true; Layout.fillHeight: true
                                text: libraryFilter
                                placeholderText: "Search your library…"
                                placeholderTextColor: themeColors.subtle
                                color: themeColors.text
                                background: null
                                font.pixelSize: 11
                                leftPadding: 0; topPadding: 0; bottomPadding: 0
                                verticalAlignment: TextInput.AlignVCenter
                                onTextChanged: { libraryFilter = text; libraryPageSize = 100 }
                            }
                        }
                    }
                    Rectangle {
                        Layout.preferredWidth: 36; Layout.preferredHeight: 36
                        radius: 10; color: refreshMouse.containsMouse ? themeColors.panel2 : themeColors.panel; border.color: themeColors.border
                        Icon { anchors.centerIn: parent; name: "refresh"; color: themeColors.text; implicitWidth: 15; implicitHeight: 15 }
                        MouseArea { id: refreshMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.refreshLibrary() }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Icon { name: "sort"; color: themeColors.muted; implicitWidth: 13; implicitHeight: 13 }
                    Repeater {
                        model: ["Newest", "Title", "Artist"]
                        delegate: Rectangle {
                            readonly property bool on: librarySort === modelData
                            Layout.preferredHeight: 26
                            Layout.preferredWidth: sortLabel.implicitWidth + 26
                            radius: 13
                            color: on ? themeColors.activeBg : "transparent"
                            border.color: on ? themeColors.borderHi : "transparent"
                            Text { id: sortLabel; anchors.centerIn: parent; text: modelData; color: on ? themeColors.lime : themeColors.muted; font.pixelSize: 11; font.weight: Font.DemiBold }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: librarySort = modelData }
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: "Add to"; color: themeColors.subtle; font.pixelSize: 10 }
                    ComboBox {
                        id: libraryPlaylistChoice
                        model: Object.keys(playlistData).length ? Object.keys(playlistData) : ["Favorites"]
                        implicitWidth: 140; implicitHeight: 28
                        font.pixelSize: 11
                        background: Rectangle { radius: 8; color: themeColors.panel; border.color: themeColors.border }
                        contentItem: Text { leftPadding: 10; text: libraryPlaylistChoice.displayText; color: themeColors.text; verticalAlignment: Text.AlignVCenter; font.pixelSize: 11; elide: Text.ElideRight }
                    }
                }
                ColumnLayout {
                    id: libraryRows
                    Layout.fillWidth: true
                    spacing: 8
                    Repeater {
                        model: visibleLibraryItems
                        delegate: Rectangle {
                            readonly property bool current: modelData.path === playerPath
                            Layout.fillWidth: true
                            Layout.preferredHeight: 68
                            radius: 14
                            color: current ? themeColors.activeBg : libraryMouse.containsMouse ? themeColors.panel2 : themeColors.panel
                            border.color: current ? themeColors.borderHi : themeColors.border
                            Behavior on color { ColorAnimation { duration: 140 } }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12; anchors.rightMargin: 14
                                spacing: 14
                                Rectangle {
                                    Layout.preferredWidth: 46; Layout.preferredHeight: 46
                                    radius: 9; color: themeColors.panel3; clip: true
                                    Image { anchors.fill: parent; source: modelData.cover || ""; sourceSize.width: 96; sourceSize.height: 96; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                                    Icon { anchors.centerIn: parent; name: "music"; color: themeColors.lime; visible: !modelData.cover; implicitWidth: 18; implicitHeight: 18 }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text { Layout.fillWidth: true; text: modelData.title || "Untitled"; color: current ? themeColors.lime : themeColors.text; font.pixelSize: 13; font.weight: Font.Bold; elide: Text.ElideRight }
                                    Text { Layout.fillWidth: true; text: [modelData.artist || "Unknown artist", modelData.album || ""].filter(function(v) { return v }).join(" · "); color: themeColors.muted; font.pixelSize: 11; elide: Text.ElideRight }
                                }
                                Rectangle {
                                    Layout.preferredHeight: 22
                                    Layout.preferredWidth: lyricsRow.implicitWidth + 16
                                    radius: 6
                                    color: lyricsMouse.containsMouse ? themeColors.borderHi : themeColors.activeBg
                                    border.color: themeColors.borderHi
                                    RowLayout {
                                        id: lyricsRow
                                        anchors.centerIn: parent
                                        spacing: 5
                                        Icon { name: "lyrics"; color: themeColors.lime; implicitWidth: 12; implicitHeight: 12 }
                                        Text { text: "Lyrics"; color: themeColors.lime; font.pixelSize: 10; font.weight: Font.Bold }
                                    }
                                    MouseArea { id: lyricsMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: bridge.findLyrics(modelData.title || "", modelData.artist || "") }
                                }
                                Text { text: formatDuration(modelData.duration); color: themeColors.muted; font.pixelSize: 11; Layout.preferredWidth: 38; horizontalAlignment: Text.AlignRight }
                                Rectangle {
                                    Layout.preferredWidth: 34; Layout.preferredHeight: 34
                                    radius: 17
                                    color: current ? themeColors.lime : themeColors.panel3
                                    Icon { anchors.centerIn: parent; anchors.horizontalCenterOffset: current && playerPlaying ? 0 : 1; name: current && playerPlaying ? "pause" : "play"; color: current ? "#14190b" : themeColors.muted; implicitWidth: 14; implicitHeight: 14 }
                                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { if (current) bridge.togglePlayback(); else bridge.playFile(modelData.path) } }
                                }
                                BarButton {
                                    icon: "list-plus"
                                    onClicked: bridge.addFileToPlaylist(libraryPlaylistChoice.currentText || "Favorites", modelData.path)
                                }
                            }
                            MouseArea { id: libraryMouse; anchors.fill: parent; hoverEnabled: true; z: -1; onDoubleClicked: bridge.playFile(modelData.path) }
                        }
                    }
                    Btn {
                        visible: visibleLibraryItems.length < filteredLibraryItems.length
                        text: "Load " + Math.min(100, filteredLibraryItems.length - visibleLibraryItems.length) + " more"
                        icon: "chevrons-down"
                        Layout.alignment: Qt.AlignHCenter
                        onClicked: libraryPageSize = Math.min(filteredLibraryItems.length, libraryPageSize + 100)
                    }
                    Text {
                        visible: filteredLibraryItems.length === 0
                        Layout.fillWidth: true; Layout.topMargin: 40
                        horizontalAlignment: Text.AlignHCenter
                        text: "No songs yet. Download something and it will appear here."
                        color: themeColors.subtle; font.pixelSize: 12
                    }
                }
                Item { Layout.preferredHeight: 24 }
            }
        }
    }

    Component {
        id: playlistsPage
        Item {
            readonly property var names: Object.keys(playlistData).sort()
            Component.onCompleted: { if (!playlistData[selectedPlaylist] && names.length) selectedPlaylist = names[0] }
            RowLayout {
                anchors.fill: parent
                spacing: 0
                Rectangle {
                    Layout.preferredWidth: 272
                    Layout.fillHeight: true
                    color: "transparent"
                    Rectangle { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right; width: 1; color: themeColors.border }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.rightMargin: 1
                        spacing: 0
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.margins: 16
                            spacing: 10
                            Text { text: "Playlists"; color: themeColors.text; font.pixelSize: 20; font.weight: Font.Bold; font.letterSpacing: -0.4 }
                            Text { Layout.fillWidth: true; text: "Your own mixes — built from the songs in your library."; color: themeColors.muted; font.pixelSize: 11; wrapMode: Text.WordWrap; lineHeight: 1.25 }
                            Btn { text: "New playlist"; icon: "plus"; primary: true; implicitHeight: 34; onClicked: { playlistNewOpen = !playlistNewOpen; if (playlistNewOpen) newPlaylistField.forceActiveFocus() } }
                            Rectangle {
                                visible: playlistNewOpen
                                Layout.fillWidth: true
                                Layout.preferredHeight: 38
                                radius: 10; color: themeColors.panel; border.color: newPlaylistField.activeFocus ? themeColors.borderHi : themeColors.border
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12; anchors.rightMargin: 6
                                    TextField {
                                        id: newPlaylistField
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
                                        Layout.fillWidth: true; Layout.fillHeight: true
                                        placeholderText: "Playlist name"
                                        placeholderTextColor: themeColors.subtle
                                        color: themeColors.text
                                        background: null
                                        font.pixelSize: 12
                                        leftPadding: 0
                                        verticalAlignment: TextInput.AlignVCenter
                                        function create() {
                                            var n = text.trim()
                                            if (!n.length) return
                                            bridge.createPlaylist(n, "[]")
                                            selectedPlaylist = n
                                            text = ""
                                            playlistNewOpen = false
                                        }
                                        onAccepted: create()
                                    }
                                    SquareButton { implicitWidth: 28; implicitHeight: 28; icon: "check"; accent: true; onClicked: newPlaylistField.create() }
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: themeColors.border }
                        Flickable {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            contentWidth: width
                            contentHeight: plListCol.implicitHeight + 16
                            ScrollBar.vertical: ScrollBar { active: true }
                            ColumnLayout {
                                id: plListCol
                                width: parent.width - 20
                                x: 10
                                spacing: 4
                                Item { Layout.preferredHeight: 6 }
                                Text { visible: names.length === 0; Layout.margins: 6; text: "No playlists yet"; color: themeColors.subtle; font.pixelSize: 12 }
                                Repeater {
                                    model: names
                                    delegate: Rectangle {
                                        readonly property bool on: selectedPlaylist === modelData
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 52
                                        radius: 10
                                        color: on ? themeColors.activeBg : (plMouse.containsMouse ? themeColors.hover : "transparent")
                                        border.color: on ? themeColors.borderHi : "transparent"
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 10; anchors.rightMargin: 10
                                            spacing: 11
                                            CoverBox { box: 34; corner: 8; fallback: "playlist" }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                Text { Layout.fillWidth: true; text: modelData; color: on ? themeColors.text : themeColors.muted; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                                Text { text: (playlistData[modelData] || []).length + " songs"; color: themeColors.subtle; font.pixelSize: 10 }
                                            }
                                        }
                                        MouseArea { id: plMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: selectedPlaylist = modelData }
                                    }
                                }
                            }
                        }
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    EmptyState {
                        visible: !playlistData[selectedPlaylist]
                        anchors.centerIn: parent
                        icon: "playlist"
                        title: "No playlists yet"
                        body: "Make one here, then add songs from your Library with the list-plus button. Playlists keep your own order."
                    }
                    Flickable {
                        visible: !!playlistData[selectedPlaylist]
                        anchors.fill: parent
                        clip: true
                        contentWidth: width
                        contentHeight: plDetail.implicitHeight + 40
                        ScrollBar.vertical: ScrollBar { active: true }
                        ColumnLayout {
                            id: plDetail
                            width: Math.min(parent.width - 64, 900)
                            anchors.horizontalCenter: parent.horizontalCenter
                            spacing: 0
                            Item { Layout.preferredHeight: 28 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 20
                                CoverBox { box: 96; corner: 10; fallback: "playlist" }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Text { text: "Playlist"; color: themeColors.lime; font.pixelSize: 11; font.weight: Font.Bold }
                                    Text { Layout.fillWidth: true; text: selectedPlaylist; color: themeColors.text; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.5; elide: Text.ElideRight }
                                    Text { text: selectedPlaylistItems.length + (selectedPlaylistItems.length === 1 ? " song" : " songs"); color: themeColors.muted; font.pixelSize: 13 }
                                }
                                Btn { text: "Play"; icon: "play"; primary: true; implicitHeight: 40; enabled: selectedPlaylistItems.length > 0; onClicked: bridge.playPlaylist(selectedPlaylist) }
                                SquareButton { implicitWidth: 40; implicitHeight: 40; radius: 10; icon: "trash"; glyph: 16; onClicked: { var n = selectedPlaylist; selectedPlaylist = ""; bridge.removePlaylist(n) } }
                            }
                            Item { Layout.preferredHeight: 22 }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: themeColors.border }
                            Text {
                                visible: selectedPlaylistItems.length === 0
                                Layout.fillWidth: true; Layout.topMargin: 40
                                horizontalAlignment: Text.AlignHCenter
                                text: "This playlist is empty. Add tracks from your Library with the list-plus button."
                                color: themeColors.subtle; font.pixelSize: 12
                            }
                            Repeater {
                                model: visiblePlaylistItems
                                delegate: Item {
                                    readonly property bool current: modelData.path === playerPath
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 60
                                    Rectangle { anchors.fill: parent; color: current ? themeColors.activeBg : (plRowMouse.containsMouse ? themeColors.panel2 : "transparent"); radius: 10 }
                                    MouseArea { id: plRowMouse; anchors.fill: parent; hoverEnabled: true; onDoubleClicked: bridge.playFile(modelData.path) }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12; anchors.rightMargin: 12
                                        spacing: 14
                                        Text { Layout.preferredWidth: 22; text: index + 1; color: themeColors.subtle; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter }
                                        CoverBox { source: modelData.cover || ""; box: 40; corner: 6 }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Text { Layout.fillWidth: true; text: modelData.title; color: current ? themeColors.lime : themeColors.text; font.pixelSize: 13; font.weight: Font.Bold; elide: Text.ElideRight }
                                            Text { Layout.fillWidth: true; text: modelData.artist; color: themeColors.muted; font.pixelSize: 12; elide: Text.ElideRight }
                                        }
                                        Text { text: formatDuration(modelData.duration); color: themeColors.muted; font.pixelSize: 12 }
                                        SquareButton { icon: current && playerPlaying ? "pause" : "play"; accent: current; onClicked: { if (current) bridge.togglePlayback(); else bridge.playFile(modelData.path) } }
                                    }
                                }
                            }
                            Btn {
                                visible: visiblePlaylistItems.length < selectedPlaylistItems.length
                                text: "Load " + Math.min(100, selectedPlaylistItems.length - visiblePlaylistItems.length) + " more"
                                icon: "chevrons-down"
                                Layout.alignment: Qt.AlignHCenter
                                onClicked: playlistPageSize = Math.min(selectedPlaylistItems.length, playlistPageSize + 100)
                            }
                            Item { Layout.preferredHeight: 20 }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: converterPage
        Flickable {
            clip: true
 contentWidth: width
 contentHeight: converterColumn.implicitHeight + 50
            ColumnLayout {
                id: converterColumn
 width: Math.min(parent.width - 100, 1040)
 anchors.horizontalCenter: parent.horizontalCenter
 spacing: 18
                Item { Layout.preferredHeight: 14 }
                Text { text: "MEDIA CONVERTER"
 color: themeColors.lime
 font.pixelSize: 9
 font.letterSpacing: 1.4 }
                Text { text: "Shape your media."
 color: themeColors.text
 font.pixelSize: 34
 font.bold: true }
                Text { text: "Convert local files using your installed FFmpeg engine."
 color: themeColors.muted
 font.pixelSize: 11 }
                Rectangle {
                    Layout.fillWidth: true
 radius: 12
 color: themeColors.panel
 border.color: themeColors.border
 implicitHeight: 270
                    ColumnLayout {
                        anchors.fill: parent
 anchors.margins: 18
 spacing: 13
                        Text { text: "CONVERSION"
 color: themeColors.lime
 font.pixelSize: 9
 font.letterSpacing: 1 }
                        RowLayout {
                            TextField { id: conversionSource
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
 Layout.fillWidth: true
 placeholderText: "Choose a local media file…"
 color: themeColors.text
 placeholderTextColor: themeColors.subtle
 background: Rectangle { radius: 7
 color: themeColors.panel2
 border.color: themeColors.border } }
                            Button { text: "Browse"
 onClicked: bridge.chooseConversionSource()
 background: Rectangle { radius: 7
 color: themeColors.panel2
 border.color: themeColors.border }
 contentItem: Text { text: parent.text
 color: themeColors.text
 font.pixelSize: 10
 horizontalAlignment: Text.AlignHCenter
 verticalAlignment: Text.AlignVCenter
 padding: 8 } }
                        }
                        AdvancedDownloadPanel {
                            id: conversionAdvancedPanel
                            Layout.fillWidth: true
                            palette: window.themeColors
                            presets: window.presets
                            selectedPreset: window.conversionPresetName
                            showSourceQuality: false
                            onPresetChanged: function(name) { window.conversionPresetName = name }
                            onSavePresetRequested: function(optionsJson) {
                                var savedName = bridge.saveCustomPreset(optionsJson)
                                if (savedName)
                                    window.conversionPresetName = savedName
                            }
                        }
                        Button { text: "Add conversion to queue  →"
 onClicked: bridge.enqueueConversionWithAdvancedOptions(conversionSource.text, JSON.stringify(conversionAdvancedPanel.options()))
 background: Rectangle { radius: 8
 color: themeColors.lime }
 contentItem: Text { text: parent.text
 color: "#14190b"
 font.bold: true
 font.pixelSize: 11
 horizontalAlignment: Text.AlignHCenter
 verticalAlignment: Text.AlignVCenter
 padding: 10 } }
                    }
                }
            }
        }
    }

    Component {
        id: settingsPage
        Item {
            Rectangle {
                id: setHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 96
                color: "transparent"
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: themeColors.border }
                ColumnLayout {
                    width: Math.min(parent.width - 100, 900)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5
                    Text { text: "Settings"; color: themeColors.text; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.6 }
                    Text { text: "Fine-tune downloads, connection, appearance, and app updates."; color: themeColors.muted; font.pixelSize: 12 }
                }
            }
            Flickable {
                anchors.top: setHeader.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                clip: true
                contentWidth: width
                contentHeight: settingsColumn.implicitHeight + 50
                ScrollBar.vertical: ScrollBar { active: true }
                ColumnLayout {
                    id: settingsColumn
                    width: Math.min(parent.width - 100, 900)
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 16
                    Item { Layout.preferredHeight: 6 }

                    SettingsCard {
                        icon: "folder"
                        title: "Downloads folder"
                        description: "Finished albums and tracks are organized inside this folder."
                        trailing: [
                            Btn { text: "Open folder"; icon: "folder"; implicitHeight: 34; onClicked: bridge.openOutputFolder() },
                            Btn { text: "Change folder"; primary: true; implicitHeight: 34; onClicked: bridge.chooseOutputFolder() }
                        ]
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 44
                            radius: 10; color: themeColors.bg; border.color: themeColors.border
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14; anchors.rightMargin: 14
                                spacing: 10
                                Icon { name: "hard-drive"; color: themeColors.subtle; implicitWidth: 15; implicitHeight: 15 }
                                Text { Layout.fillWidth: true; text: settingsData.output_dir || ""; color: themeColors.text; font.pixelSize: 12; font.family: "monospace"; elide: Text.ElideMiddle }
                            }
                        }
                    }

                    SettingsCard {
                        icon: "file-text"
                        title: "Download synchronized lyrics"
                        description: "Automatically fetch timestamped lyrics after music downloads and save them next to the audio as .LRC. Local LRC files are used first when you open the lyrics view."
                        trailing: Segmented {
                            options: ["On", "Off"]
                            current: settingsData.download_lyrics === false ? "Off" : "On"
                            onPicked: function(value) {
                                bridge.setSetting("download_lyrics", value === "On" ? "true" : "false")
                            }
                        }
                    }

                    SettingsCard {
                        icon: "keyboard"
                        title: "Keyboard shortcuts"
                        description: "Media shortcuts work throughout the app and pause while you are typing in a text field."
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 7
                            Repeater {
                                model: [
                                    {keys: "Space", action: "Play / pause"},
                                    {keys: "Ctrl + ← / →", action: "Previous / next track"},
                                    {keys: "Ctrl + L", action: "Open lyrics"},
                                    {keys: "Shift + ← / →", action: "Seek 5 seconds"},
                                    {keys: "M", action: "Mute / unmute"},
                                    {keys: "Ctrl + ↑ / ↓", action: "Volume up / down"},
                                    {keys: "Ctrl + K", action: "Focus search"}
                                ]
                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 12
                                    Text {
                                        Layout.preferredWidth: 128
                                        text: modelData.keys
                                        color: themeColors.text
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                        font.family: "Segoe UI"
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.action
                                        color: themeColors.muted
                                        font.pixelSize: 11
                                    }
                                }
                            }
                        }
                    }

                    SettingsCard {
                        icon: "sun"
                        title: "Appearance"
                        description: "Choose how Universal Media Studio looks."
                        trailing: Segmented {
                            options: ["Dark", "Light"]
                            current: settingsData.theme || "Dark"
                            onPicked: function(value) { bridge.setSetting("theme", value) }
                        }
                    }

                    SettingsCard {
                        icon: "wrench"
                        title: "Local tools"
                        description: "Downloads and conversions run on this computer with these tools."
                        trailing: Btn { text: "Refresh"; icon: "refresh"; implicitHeight: 34; onClicked: { bridge.diagnostics(); diagnosticsData = JSON.parse(bridge.statusJson()) } }
                        Repeater {
                            model: [
                                {label: "yt-dlp", value: diagnosticsData.yt_dlp},
                                {label: "FFmpeg", value: diagnosticsData.ffmpeg},
                                {label: "FFprobe", value: diagnosticsData.ffprobe}
                            ]
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 40
                                radius: 10; color: themeColors.bg; border.color: themeColors.border
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 14; anchors.rightMargin: 14
                                    spacing: 12
                                    Text { Layout.preferredWidth: 70; text: modelData.label; color: themeColors.text; font.pixelSize: 12; font.weight: Font.Bold }
                                    Text { Layout.fillWidth: true; text: modelData.value || "checking…"; color: themeColors.muted; font.pixelSize: 11; font.family: "monospace"; elide: Text.ElideMiddle }
                                }
                            }
                        }
                    }

                    SettingsCard {
                        icon: "network"
                        title: "Connection"
                        description: "Universal Media Studio reaches the music services from this computer. If they are filtered where you are, send it through your VPN."
                        trailing: Segmented {
                            options: ["Automatic", "Proxy", "Direct"]
                            current: settingsData.connection_mode || "Automatic"
                            onPicked: function(value) { bridge.setSetting("connection_mode", value) }
                        }
                        Text {
                            text: (settingsData.connection_mode || "Automatic") === "Automatic" ? "Follow the system proxy settings, as your browser does."
                                : ((settingsData.connection_mode === "Proxy") ? "Send everything through the proxy address below." : "Connect straight to the internet and ignore any proxy.")
                            color: themeColors.subtle; font.pixelSize: 11
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 44
                            radius: 10; color: themeColors.bg; border.color: themeColors.border
                            Text { anchors.fill: parent; anchors.leftMargin: 14; verticalAlignment: Text.AlignVCenter; text: bridge.detectedProxy(); color: themeColors.text; font.pixelSize: 12; elide: Text.ElideRight }
                        }
                        Rectangle {
                            visible: settingsData.connection_mode === "Proxy"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 44
                            radius: 10; color: themeColors.bg; border.color: proxyUrlField.activeFocus ? themeColors.borderHi : themeColors.border
                            TextField {
                                id: proxyUrlField
                                onActiveFocusChanged: window.keyboardTextEntryActive = activeFocus
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                placeholderText: "Proxy URL (for example, http://127.0.0.1:8080)"
                                placeholderTextColor: themeColors.subtle
                                text: settingsData.proxy_url || ""
                                color: themeColors.text
                                background: null
                                font.pixelSize: 12
                                verticalAlignment: TextInput.AlignVCenter
                                onEditingFinished: bridge.setSetting("proxy_url", text)
                            }
                        }
                        RowLayout {
                            spacing: 8
                            Btn { text: "Find my VPN's proxy"; icon: "network"; implicitHeight: 34; onClicked: bridge.findProxyHelp() }
                            Btn { text: "Test connection"; icon: "activity"; implicitHeight: 34; onClicked: bridge.testConnection() }
                        }
                    }

                    SettingsCard {
                        icon: "cookie"
                        title: "Browser cookies"
                        description: "If YouTube asks for a sign-in mid-download, pick the browser you are signed into YouTube in. Downloads use your own account, on your own machine."
                        trailing: StyledCombo {
                            id: cookiesBrowserBox
                            implicitWidth: 190
                            readonly property var entries: [{label: "Off", browser: "None", profile: ""}].concat(browserProfiles)
                            model: entries
                            textRole: "label"
                            currentIndex: {
                                if (!settingsData.cookies_browser || settingsData.cookies_browser === "None") return 0
                                for (var i = 1; i < entries.length; i++)
                                    if (entries[i].browser === settingsData.cookies_browser && entries[i].profile === (settingsData.cookies_profile || "")) return i
                                return 0
                            }
                            onActivated: function(index) {
                                var sel = entries[index]
                                if (!sel) return
                                bridge.setSetting("cookies_browser", sel.browser)
                                bridge.setSetting("cookies_profile", sel.profile)
                            }
                        }
                        RowLayout {
                            spacing: 10
                            Btn { text: "Refresh browser detection"; icon: "refresh"; implicitHeight: 34; onClicked: browserProfiles = JSON.parse(bridge.browserProfilesJson()) }
                            Text { text: browserProfiles.length + " profile(s) found"; color: themeColors.subtle; font.pixelSize: 11 }
                        }
                    }

                    SettingsCard {
                        icon: "file-text"
                        title: "Application logs"
                        description: "View or export startup, QML, worker, FFmpeg, and download diagnostics. Logs rotate automatically to limit disk use. Review URLs and local paths before sharing."
                        trailing: [
                            Btn {
                                text: "View logs"
                                icon: "file-text"
                                implicitHeight: 34
                                onClicked: {
                                    applicationLogText = bridge.readLog()
                                    logDialog.open()
                                }
                            },
                            Btn {
                                text: "Export log"
                                icon: "download"
                                primary: true
                                implicitHeight: 34
                                onClicked: bridge.exportLog()
                            }
                        ]
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: bridge.logPath()
                                color: themeColors.subtle
                                font.pixelSize: 10
                                font.family: "monospace"
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                            Btn {
                                text: "Open file"
                                icon: "external-link"
                                implicitHeight: 32
                                onClicked: bridge.openLogFile()
                            }
                        }
                    }

                    SettingsCard {
                        icon: "sparkles"
                        title: "About Universal Media Studio"
                        description: "App version 0.3.0. Update check opens the project releases page in your browser."
                        trailing: Btn { text: "Check for updates"; icon: "refresh"; implicitHeight: 34; onClicked: bridge.checkForUpdates() }
                    }
                    Item { Layout.preferredHeight: 20 }
                }
            }
        }
    }

    Dialog {
        id: analysisDialog
        modal: true
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(940, window.width - 32)
        height: Math.min(720, window.height - 32)
        padding: 0
        standardButtons: Dialog.NoButton
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: themeColors.panel
            radius: 18
            border.color: themeColors.border
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 12

                Rectangle {
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    radius: 11
                    color: themeColors.activeBg
                    Icon {
                        anchors.centerIn: parent
                        name: "search"
                        color: themeColors.lime
                        implicitWidth: 20
                        implicitHeight: 20
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: "MEDIA INSPECTOR"
                        color: themeColors.lime
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1.5
                    }
                    Text {
                        text: window.analysisBusy ? "Analyzing URL" :
                              (window.analysisError.length ? "Couldn’t inspect this source" : "Media information")
                        color: themeColors.text
                        font.pixelSize: 19
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: window.analysisBusy
                              ? "Fetching source details and available formats"
                              : (window.analysisError.length
                                 ? "Check the URL or try again."
                                 : (window.analysisData.extractor || "Media source") +
                                   "  ·  " + (window.analysisData.formats || []).length + " formats found")
                        color: themeColors.muted
                        font.pixelSize: 10
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                Rectangle {
                    visible: window.analysisBusy
                    radius: 9
                    color: themeColors.panel2
                    border.color: themeColors.border
                    Layout.preferredWidth: 88
                    Layout.preferredHeight: 30
                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 6
                        BusyIndicator {
                            running: window.analysisBusy
                            Layout.preferredWidth: 14
                            Layout.preferredHeight: 14
                        }
                        Text { text: "Working"; color: themeColors.muted; font.pixelSize: 10 }
                    }
                }

                Btn {
                    text: "Close"
                    icon: "x"
                    implicitHeight: 32
                    onClicked: analysisDialog.close()
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: themeColors.border }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 240

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 22
                    spacing: 13
                    visible: window.analysisBusy

                    Item { Layout.fillHeight: true }
                    BusyIndicator {
                        running: window.analysisBusy
                        Layout.preferredWidth: 54
                        Layout.preferredHeight: 54
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: "Inspecting source metadata"
                        color: themeColors.text
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: window.analysisTargetUrl
                        color: themeColors.subtle
                        font.pixelSize: 10
                        elide: Text.ElideMiddle
                        horizontalAlignment: Text.AlignHCenter
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "Reading the title, channel, preview image, media properties and available formats. No media is being downloaded."
                        color: themeColors.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        Layout.maximumWidth: 470
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Item { Layout.fillHeight: true }
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 13
                    visible: !window.analysisBusy && window.analysisError.length > 0

                    Item { Layout.fillHeight: true }
                    Rectangle {
                        Layout.preferredWidth: 54
                        Layout.preferredHeight: 54
                        radius: 15
                        color: "#2b1716"
                        Layout.alignment: Qt.AlignHCenter
                        Icon { anchors.centerIn: parent; name: "alert"; color: themeColors.danger; implicitWidth: 24; implicitHeight: 24 }
                    }
                    Text {
                        text: "Analysis failed"
                        color: themeColors.text
                        font.pixelSize: 17
                        font.weight: Font.Bold
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: window.analysisError
                        color: themeColors.danger
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        Layout.maximumWidth: 620
                        Layout.alignment: Qt.AlignHCenter
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 8
                        Btn {
                            text: "Try again"
                            icon: "refresh"
                            primary: true
                            implicitHeight: 34
                            enabled: window.analysisTargetUrl.length > 0
                            onClicked: {
                                window.analysisBusy = true
                                window.analysisError = ""
                                window.analysisData = ({})
                                window.analysisThumbnailList = []
                                window.analysisThumbnailIndex = 0
                                bridge.analyzeUrl(window.analysisTargetUrl, "download")
                            }
                        }
                        Btn { text: "Close"; implicitHeight: 34; onClicked: analysisDialog.close() }
                    }
                    Item { Layout.fillHeight: true }
                }

                ScrollView {
                    id: analysisScroll
                    anchors.fill: parent
                    anchors.margins: 14
                    clip: true
                    visible: !window.analysisBusy && window.analysisError.length === 0 && !!window.analysisData.title
                    // Give the scroll content the viewport width explicitly.
                    // Otherwise implicitWidth <-> parent.width can collapse
                    // the inspector and make all child layouts overlap.
                    contentWidth: availableWidth
                    ScrollBar.vertical: ScrollBar { active: true }

                    ColumnLayout {
                        id: analysisContent
                        width: analysisScroll.availableWidth
                        spacing: 12

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: analysisScroll.availableWidth
                            radius: 13
                            color: themeColors.panel2
                            border.color: themeColors.border
                            implicitHeight: 204
                            clip: true

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 16

                                Rectangle {
                                    Layout.minimumWidth: 180
                                    Layout.maximumWidth: 300
                                    Layout.preferredWidth: Math.min(300, Math.max(180, analysisContent.width * 0.34))
                                    Layout.preferredHeight: Layout.preferredWidth * 9 / 16
                                    Layout.fillHeight: true
                                    radius: 9
                                    color: themeColors.panel3
                                    border.color: themeColors.border
                                    clip: true

                                    Image {
                                        id: preview
                                        anchors.fill: parent
                                        source: window.analysisThumbnailList.length > 0
                                                ? window.analysisThumbnailList[window.analysisThumbnailIndex]
                                                : (window.analysisData.thumbnail || "")
                                        asynchronous: true
                                        cache: true
                                        sourceSize.width: 900
                                        sourceSize.height: 506
                                        fillMode: Image.PreserveAspectCrop
                                        visible: status === Image.Ready
                                        onStatusChanged: {
                                            if (status === Image.Error &&
                                                window.analysisThumbnailIndex + 1 < window.analysisThumbnailList.length) {
                                                window.analysisThumbnailIndex++
                                            }
                                        }
                                    }

                                    ColumnLayout {
                                        anchors.centerIn: parent
                                        visible: preview.status !== Image.Ready
                                        spacing: 7
                                        Rectangle {
                                            Layout.preferredWidth: 38
                                            Layout.preferredHeight: 38
                                            radius: 11
                                            color: themeColors.panel2
                                            Layout.alignment: Qt.AlignHCenter
                                            Icon { anchors.centerIn: parent; name: "image"; color: themeColors.subtle; implicitWidth: 19; implicitHeight: 19 }
                                        }
                                        Text {
                                            text: preview.status === Image.Loading ? "Loading preview…" : "Preview unavailable"
                                            color: themeColors.subtle
                                            font.pixelSize: 10
                                            Layout.alignment: Qt.AlignHCenter
                                        }
                                    }

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.bottom: parent.bottom
                                        anchors.margins: 9
                                        radius: 6
                                        color: "#b0000000"
                                        width: sourceBadge.implicitWidth + 14
                                        height: 23
                                        Text {
                                            id: sourceBadge
                                            anchors.centerIn: parent
                                            text: window.analysisData.extractor || "MEDIA"
                                            color: "#ffffff"
                                            font.pixelSize: 9
                                            font.weight: Font.Bold
                                        }
                                    }
                                }

                                ColumnLayout {
                                    Layout.minimumWidth: 0
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: 8

                                    Text {
                                        Layout.minimumWidth: 0
                                        text: window.analysisData.title || "Untitled media"
                                        color: themeColors.text
                                        font.pixelSize: 18
                                        font.weight: Font.Bold
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: 3
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }

                                    Text {
                                        Layout.minimumWidth: 0
                                        text: window.analysisData.uploader || window.analysisData.channel ||
                                              window.analysisData.creator || "Unknown creator"
                                        color: themeColors.muted
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }

                                    Text {
                                        Layout.minimumWidth: 0
                                        text: window.analysisData.channel_url || window.analysisData.webpage_url || ""
                                        color: themeColors.subtle
                                        font.pixelSize: 9
                                        elide: Text.ElideMiddle
                                        Layout.fillWidth: true
                                    }

                                    RowLayout {
                                        spacing: 7
                                        Rectangle {
                                            radius: 6
                                            color: themeColors.activeBg
                                            implicitWidth: liveLabel.implicitWidth + 14
                                            implicitHeight: 23
                                            Text {
                                                id: liveLabel
                                                anchors.centerIn: parent
                                                text: window.analysisData.is_live ? "LIVE" : (window.analysisData.ext || "MEDIA").toUpperCase()
                                                color: themeColors.lime
                                                font.pixelSize: 9
                                                font.weight: Font.Bold
                                            }
                                        }
                                        Text {
                                            text: window.analysisData.resolution || "Resolution not supplied"
                                            color: themeColors.muted
                                            font.pixelSize: 10
                                        }
                                        Text {
                                            visible: Number(window.analysisData.fps) > 0
                                            text: "· " + Number(window.analysisData.fps).toFixed(2).replace(/\.00$/, "") + " FPS"
                                            color: themeColors.muted
                                            font.pixelSize: 10
                                        }
                                    }
                                }
                            }
                        }

                        Flow {
                            id: analysisMetadataFlow
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: analysisScroll.availableWidth
                            Layout.preferredHeight: Math.ceil(metadataRepeater.count / metadataColumns) * 66 - 9
                            spacing: 9
                            property int metadataColumns: analysisDialog.width < 680 ? 2 : 4

                            Repeater {
                                id: metadataRepeater
                                model: [
                                    {label: "DURATION", value: window.analysisData.is_live ? "Live" : window.formatMediaDuration(window.analysisData.duration)},
                                    {label: "RESOLUTION", value: window.analysisData.resolution || "—"},
                                    {label: "FRAME RATE", value: Number(window.analysisData.fps) > 0 ? Number(window.analysisData.fps).toFixed(2).replace(/\.00$/, "") + " FPS" : "—"},
                                    {label: "VIEWS", value: window.displayCount(window.analysisData.view_count)},
                                    {label: "LIKES", value: window.displayCount(window.analysisData.like_count)},
                                    {label: "PUBLISHED", value: window.displayMediaDate(window.analysisData.upload_date || window.analysisData.release_date)},
                                    {label: "FILE SIZE", value: window.displayMediaSize(window.analysisData.filesize)},
                                    {label: "VIDEO CODEC", value: window.analysisData.vcodec || "—"},
                                    {label: "AUDIO CODEC", value: window.analysisData.acodec || "—"},
                                    {label: "FORMATS", value: String((window.analysisData.formats || []).length)},
                                    {label: "SUBTITLES", value: String((window.analysisData.subtitles || []).length + (window.analysisData.automatic_captions || []).length)},
                                    {label: "MEDIA ID", value: window.analysisData.id || "—"}
                                ]
                                delegate: Rectangle {
                                    width: Math.max(1, (analysisMetadataFlow.width - analysisMetadataFlow.spacing * (analysisMetadataFlow.metadataColumns - 1)) / analysisMetadataFlow.metadataColumns)
                                    height: 57
                                    radius: 9
                                    color: themeColors.panel2
                                    border.color: themeColors.border
                                    Column {
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 4
                                        Text {
                                            width: parent.width
                                            text: modelData.label
                                            color: themeColors.subtle
                                            font.pixelSize: 8
                                            font.weight: Font.Bold
                                            font.letterSpacing: 0.7
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            width: parent.width
                                            text: String(modelData.value || "—")
                                            color: themeColors.text
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: analysisScroll.availableWidth
                            radius: 11
                            color: themeColors.panel2
                            border.color: themeColors.border
                            implicitHeight: descriptionColumn.implicitHeight + 24
                            ColumnLayout {
                                id: descriptionColumn
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 7
                                Text { text: "DESCRIPTION"; color: themeColors.lime; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.1 }
                                Text {
                                    Layout.fillWidth: true
                                    text: window.analysisData.description || "No description was supplied by the source."
                                    color: themeColors.muted
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 6
                                    elide: Text.ElideRight
                                }
                                Text {
                                    visible: (window.analysisData.tags || []).length > 0
                                    Layout.fillWidth: true
                                    text: "Tags  ·  " + (window.analysisData.tags || []).slice(0, 20).join("  ·  ")
                                    color: themeColors.subtle
                                    font.pixelSize: 9
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: analysisScroll.availableWidth
                            radius: 11
                            color: themeColors.panel2
                            border.color: themeColors.border
                            implicitHeight: formatsColumn.implicitHeight + 22
                            ColumnLayout {
                                id: formatsColumn
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "AVAILABLE FORMATS"; color: themeColors.lime; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.1 }
                                    Item { Layout.fillWidth: true }
                                    Text { text: (window.analysisData.formats || []).length + " streams"; color: themeColors.subtle; font.pixelSize: 9 }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "ID"; color: themeColors.subtle; font.pixelSize: 8; Layout.preferredWidth: 44 }
                                    Text { text: "CONTAINER"; color: themeColors.subtle; font.pixelSize: 8; Layout.preferredWidth: 72 }
                                    Text { text: "RESOLUTION"; color: themeColors.subtle; font.pixelSize: 8; Layout.preferredWidth: 105 }
                                    Text { text: "FPS"; color: themeColors.subtle; font.pixelSize: 8; Layout.preferredWidth: 48 }
                                    Text { text: "SIZE"; color: themeColors.subtle; font.pixelSize: 8; Layout.preferredWidth: 68 }
                                    Text { text: "VIDEO / AUDIO"; color: themeColors.subtle; font.pixelSize: 8; Layout.fillWidth: true }
                                }

                                Repeater {
                                    model: (window.analysisData.formats || []).slice(0, 16)
                                    delegate: Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 29
                                        radius: 5
                                        color: index % 2 === 0 ? themeColors.panel3 : "transparent"
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 7
                                            anchors.rightMargin: 7
                                            spacing: 6
                                            Text { text: String(modelData.format_id || "—"); color: themeColors.text; font.pixelSize: 9; Layout.preferredWidth: 44 }
                                            Text { text: String(modelData.ext || "—").toUpperCase(); color: themeColors.muted; font.pixelSize: 9; Layout.preferredWidth: 72 }
                                            Text { text: String(modelData.resolution || "—"); color: themeColors.muted; font.pixelSize: 9; Layout.preferredWidth: 105 }
                                            Text { text: modelData.fps ? String(modelData.fps) : "—"; color: themeColors.muted; font.pixelSize: 9; Layout.preferredWidth: 48 }
                                            Text { text: window.displayMediaSize(modelData.filesize); color: themeColors.muted; font.pixelSize: 9; Layout.preferredWidth: 68 }
                                            Text {
                                                text: [modelData.vcodec, modelData.acodec].filter(function(v){ return v && v !== "none" }).join(" / ") || "—"
                                                color: themeColors.subtle
                                                font.pixelSize: 9
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: themeColors.border }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                Layout.topMargin: 11
                Layout.bottomMargin: 13
                spacing: 8

                Text {
                    text: window.analysisData.webpage_url || window.analysisTargetUrl
                    color: themeColors.subtle
                    font.pixelSize: 9
                    elide: Text.ElideMiddle
                    Layout.fillWidth: true
                }

                Btn {
                    visible: !window.analysisBusy && !window.analysisError.length && !!window.analysisData.webpage_url
                    text: "Open source"
                    icon: "external-link"
                    implicitHeight: 32
                    onClicked: Qt.openUrlExternally(window.analysisData.webpage_url)
                }

                Btn {
                    text: window.analysisError.length ? "Done" : "Close"
                    primary: true
                    implicitHeight: 32
                    onClicked: analysisDialog.close()
                }
            }
        }
    }
    Dialog {
        id: logDialog
        modal: true
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(980, window.width - 36)
        height: Math.min(700, window.height - 36)
        padding: 0
        standardButtons: Dialog.NoButton
        closePolicy: Popup.CloseOnEscape
        background: Rectangle {
            color: themeColors.panel
            radius: 16
            border.color: themeColors.border
        }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text { text: "DIAGNOSTICS"; color: themeColors.lime; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.3 }
                    Text { text: "Application log"; color: themeColors.text; font.pixelSize: 19; font.weight: Font.Bold }
                    Text { text: bridge.logPath(); color: themeColors.subtle; font.pixelSize: 9; font.family: "monospace"; elide: Text.ElideMiddle; Layout.fillWidth: true }
                }
                Btn { text: "Refresh"; icon: "refresh"; implicitHeight: 34; onClicked: applicationLogText = bridge.readLog() }
                Btn { text: "Export"; icon: "download"; primary: true; implicitHeight: 34; onClicked: bridge.exportLog() }
                Btn { text: "Close"; icon: "x"; implicitHeight: 34; onClicked: logDialog.close() }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeColors.border }
            ScrollView {
                id: logScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 14
                clip: true
                contentWidth: availableWidth
                ScrollBar.vertical: ScrollBar { active: true }
                TextArea {
                    width: logScroll.availableWidth
                    height: Math.max(logScroll.availableHeight, contentHeight + 24)
                    text: window.applicationLogText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: themeColors.text
                    selectedTextColor: themeColors.bg
                    selectionColor: themeColors.lime
                    font.family: "Consolas"
                    font.pixelSize: 10
                    background: Rectangle { color: themeColors.bg; radius: 9; border.color: themeColors.border }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeColors.border }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 14
                Text {
                    text: "Recent log output · secrets and private URLs may appear in diagnostic messages."
                    color: themeColors.subtle
                    font.pixelSize: 9
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Btn { text: "Open log file"; icon: "external-link"; implicitHeight: 32; onClicked: bridge.openLogFile() }
            }
        }
    }

    LyricsDialog {
        id: lyricsDialog
        songTitle: lyricsTitle || playerTitle
        artistName: lyricsArtist || playerArtist
        coverArt: playerCover
        lyrics: lyricsLines
        message: lyricsMessage
        lyricsSynchronized: window.lyricsSynchronized
        source: lyricsSource
        positionMs: playerPosition
        durationMs: playerDuration
        playing: playerPlaying
        accentColor: themeColors.lime
        onSeekRequested: function(position) { bridge.seekPlayer(position) }
        onTimingUnavailableClicked: toast.showMessage("These lyrics are not timestamped, so seeking is unavailable.")
        onToggleRequested: bridge.togglePlayback()
        onPreviousRequested: bridge.playPrevious()
        onNextRequested: bridge.playNext()
    }
    Popup {
        id: toast
        property string message: ""
        property bool isError: false
        function showMessage(value, error) { message = value
 isError = !!error
 open()
 closeTimer.restart() }
        x: window.width - width - 24
 y: window.height - height - 84
        width: Math.min(480, window.width - 40)
 height: 54
        background: Rectangle { radius: 9
 color: themeColors.panel3
 border.color: toast.isError ? themeColors.danger : themeColors.borderHi }
        contentItem: Text { text: toast.message
 color: themeColors.text
 verticalAlignment: Text.AlignVCenter
 leftPadding: 14
 rightPadding: 14
 font.pixelSize: 11
 wrapMode: Text.Wrap }
        Timer { id: closeTimer
 interval: 3500
 onTriggered: toast.close() }
        enter: Transition { NumberAnimation { property: "opacity"
 from: 0
 to: 1
 duration: 180 }
 NumberAnimation { property: "y"
 from: toast.y + 10
 to: toast.y
 duration: 220
 easing.type: Easing.OutCubic } }
        exit: Transition { NumberAnimation { property: "opacity"
 from: 1
 to: 0
 duration: 140 } }
    }
}
