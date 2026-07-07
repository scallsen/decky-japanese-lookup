from vnlookup.cleanup import (
    clean_ocr_text,
    filter_ui_regions,
    looks_like_japanese,
    strip_speaker_name,
)


def test_full_pipeline_vn_line():
    raw = "【玲奈】\n「そ んな こと…… 言われても、\nデ一タが 足りないよ」"
    assert clean_ocr_text(raw) == "「そんなこと…言われても、データが足りないよ」"


def test_name_quote_prefix_stripped():
    assert clean_ocr_text("玲奈「おはよう」") == "「おはよう」"


def test_speaker_kept_when_disabled():
    assert clean_ocr_text("玲奈「おはよう」", remove_speaker=False) == "玲奈「おはよう」"


def test_narration_line_not_mangled():
    line = "彼女は静かに頷いた。"
    assert clean_ocr_text(line) == line


def test_latin_spaces_collapse_but_survive():
    assert clean_ocr_text("The  Great VN  Title") == "The Great VN Title"


def test_linebreaks_joined_without_spaces():
    assert clean_ocr_text("今日は\nいい天気") == "今日はいい天気"


def test_choonpu_misread_fixed_between_kana():
    assert clean_ocr_text("デ一タ") == "データ"
    # but a real 一 between kanji is left alone
    assert clean_ocr_text("第一章") == "第一章"


def test_ellipsis_variants_normalized():
    assert clean_ocr_text("そう...だね") == "そう…だね"
    assert clean_ocr_text("そう・・・だね") == "そう…だね"


def test_empty_input():
    assert clean_ocr_text("") == ""
    assert clean_ocr_text("   \n  ") == ""


def test_strip_speaker_bracket_label():
    assert strip_speaker_name("【先生】どうした？") == "どうした？"


def test_looks_like_japanese():
    assert looks_like_japanese("こんにちは")
    assert looks_like_japanese("「データが足りない」")
    assert not looks_like_japanese("@@##%%")
    assert not looks_like_japanese("Options Save Load")
    assert not looks_like_japanese("")


def _region(text):
    return {"text": text, "rect": {}, "confidence": 0.9}


def test_filter_ui_regions_drops_ascii_scraps_next_to_japanese():
    regions = [
        _region("そんなことを言われても困る"),
        _region("Auto"),
        _region("Skip"),
        _region("Chapter 3: The Long Goodbye"),
    ]
    kept, dropped = filter_ui_regions(regions)
    assert dropped == ["Auto", "Skip"]
    assert [r["text"] for r in kept] == [
        "そんなことを言われても困る",
        "Chapter 3: The Long Goodbye",
    ]


def test_filter_ui_regions_keeps_all_when_no_japanese():
    regions = [_region("Auto"), _region("Skip")]
    kept, dropped = filter_ui_regions(regions)
    assert dropped == []
    assert len(kept) == 2
