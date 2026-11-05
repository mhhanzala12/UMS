"""Built-in output presets for Universal Media Studio."""

PRESETS = {
    "Best Available Quality": {
        "format": "bestvideo+bestaudio/best", "container": "mkv", "video_codec": "copy",
        "audio_codec": "copy", "rate_control": "Source", "fps": "Source", "resolution": "Source",
        "video_bitrate": "", "audio_bitrate": "", "crf": "20", "encoder_preset": "medium",
        "write_subtitles": True, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Smallest File": {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]", "container": "mp4",
        "video_codec": "h264", "audio_codec": "aac", "rate_control": "CRF", "fps": "Source",
        "resolution": "720p", "video_bitrate": "", "audio_bitrate": "128k", "crf": "30",
        "encoder_preset": "slow", "write_subtitles": False, "embed_subtitles": False,
        "preserve_metadata": True,
    },
    "Balanced Quality and Size": {
        "format": "bestvideo+bestaudio/best", "container": "mp4", "video_codec": "h264",
        "audio_codec": "aac", "rate_control": "CRF", "fps": "Source", "resolution": "1080p",
        "video_bitrate": "", "audio_bitrate": "192k", "crf": "23", "encoder_preset": "medium",
        "write_subtitles": True, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Mobile Compatible": {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]", "container": "mp4",
        "video_codec": "h264", "audio_codec": "aac", "rate_control": "CRF", "fps": "Source",
        "resolution": "720p", "video_bitrate": "", "audio_bitrate": "128k", "crf": "25",
        "encoder_preset": "fast", "write_subtitles": True, "embed_subtitles": False,
        "preserve_metadata": True,
    },
    "Low-End Device": {
        "format": "best[height<=480]/best", "container": "mp4", "video_codec": "h264",
        "audio_codec": "aac", "rate_control": "CBR", "fps": "30", "resolution": "480p",
        "video_bitrate": "900k", "audio_bitrate": "96k", "crf": "26", "encoder_preset": "fast",
        "write_subtitles": False, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Social Media Share": {
        "format": "bestvideo+bestaudio/best", "container": "mp4", "video_codec": "h264",
        "audio_codec": "aac", "rate_control": "VBR", "fps": "30", "resolution": "1080p",
        "video_bitrate": "6000k", "audio_bitrate": "192k", "crf": "22", "encoder_preset": "medium",
        "write_subtitles": True, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Archive Quality": {
        "format": "bestvideo+bestaudio/best", "container": "mkv", "video_codec": "copy",
        "audio_codec": "copy", "rate_control": "Source", "fps": "Source", "resolution": "Source",
        "video_bitrate": "", "audio_bitrate": "", "crf": "18", "encoder_preset": "slow",
        "write_subtitles": True, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Audio Only": {
        "format": "bestaudio/best", "container": "mp3", "video_codec": "copy",
        "audio_codec": "mp3", "rate_control": "Source", "fps": "Source", "resolution": "Source",
        "video_bitrate": "", "audio_bitrate": "192k", "crf": "20", "encoder_preset": "medium",
        "write_subtitles": False, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Lossless Audio": {
        "format": "bestaudio/best", "container": "flac", "video_codec": "copy",
        "audio_codec": "flac", "rate_control": "Source", "fps": "Source", "resolution": "Source",
        "video_bitrate": "", "audio_bitrate": "", "crf": "20", "encoder_preset": "medium",
        "write_subtitles": False, "embed_subtitles": False, "preserve_metadata": True,
    },
    "3GP Legacy Mobile": {
        "format": "best[height<=360]/best", "container": "3gp", "video_codec": "h264",
        "audio_codec": "aac", "rate_control": "CBR", "fps": "25", "resolution": "360p",
        "video_bitrate": "500k", "audio_bitrate": "64k", "crf": "28", "encoder_preset": "fast",
        "write_subtitles": False, "embed_subtitles": False, "preserve_metadata": True,
    },
    "MP4 Universal Compatibility": {
        "format": "bestvideo+bestaudio/best", "container": "mp4", "video_codec": "h264",
        "audio_codec": "aac", "rate_control": "CRF", "fps": "Source", "resolution": "Source",
        "video_bitrate": "", "audio_bitrate": "192k", "crf": "21", "encoder_preset": "medium",
        "write_subtitles": True, "embed_subtitles": False, "preserve_metadata": True,
    },
    "Web Optimized": {
        "format": "bestvideo+bestaudio/best", "container": "mp4", "video_codec": "h264",
        "audio_codec": "aac", "rate_control": "VBR", "fps": "Source", "resolution": "1080p",
        "video_bitrate": "4500k", "audio_bitrate": "160k", "crf": "23", "encoder_preset": "fast",
        "write_subtitles": True, "embed_subtitles": False, "preserve_metadata": True,
    },
}


def merged_presets(custom=None):
    result = {name: dict(value) for name, value in PRESETS.items()}
    if isinstance(custom, dict):
        for name, value in custom.items():
            if isinstance(name, str) and isinstance(value, dict):
                result[name] = dict(value)
    return result
