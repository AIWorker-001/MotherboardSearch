from src.model_identification import resolve_identification

CATALOG = ["ASUS PRIME Z390-A", "ASUS PRIME Z390-P", "MSI B450 TOMAHAWK MAX"]


def test_listing_model_is_primary_and_visual_confirmation_raises_confidence():
    result, audit = resolve_identification(["ASUS PRIME Z390-A"], ["PRIME Z390-A"], CATALOG)
    assert result.text == "ASUS PRIME Z390-A"
    assert result.source == "listing_confirmed"
    assert result.confidence > 0.95
    assert audit["agreement"] >= 0.82


def test_listing_without_visual_confirmation_remains_probable():
    result, _ = resolve_identification(["MSI B450 TOMAHAWK MAX"], [], CATALOG)
    assert result.text == "MSI B450 TOMAHAWK MAX"
    assert result.source == "listing_probable"


def test_visual_conflict_does_not_silently_replace_listing():
    result, audit = resolve_identification(["ASUS PRIME Z390-A"], ["ASUS PRIME Z390-P"], CATALOG)
    assert result.text == "ASUS PRIME Z390-A"
    assert result.source == "listing_conflict"
    assert result.confirmation == "visual_conflict"
    assert audit["visual_catalog_match"] == "ASUS PRIME Z390-P"


def test_missing_listing_uses_visual_identification():
    result, _ = resolve_identification([], ["MSI B450 TOMAHAWK MAX"], CATALOG)
    assert result.text == "MSI B450 TOMAHAWK MAX"
    assert result.source == "visually_identified"


def test_uncatalogued_listing_is_preserved_not_forced_to_wrong_catalog_model():
    result, _ = resolve_identification(["SUPERMICRO X11SCA-F"], [], CATALOG)
    assert result.text == "SUPERMICRO X11SCA-F"
    assert result.source == "listing_uncatalogued"


def test_exact_model_suffix_conflict_helper():
    from src.model_identification import exact_model_conflict
    assert exact_model_conflict("ASUS PRIME Z390-A", "ASUS PRIME Z390-P")
    assert not exact_model_conflict("ASUS PRIME Z390-A", "PRIME Z390-A")


def test_extracts_concise_legacy_asus_model():
    from src.model_identification import canonical_listing_model
    assert canonical_listing_model('ASUS P8P67 EVO Motherboard with CPU Fan and Heatsinks') == 'ASUS P8P67 EVO'


def test_extracts_b450_aorus_m_without_matching_z690():
    from src.model_identification import canonical_listing_model, best_candidate_match
    candidate=canonical_listing_model('GIGABYTE B450 AORUS M Micro-ATX AM4 Motherboard')
    assert candidate == 'GIGABYTE B450 AORUS M'
    key, score, raw=best_candidate_match([candidate,'AORUS'], ['GIGABYTE Z690 AORUS ELITE AX'])
    assert raw == candidate
    assert score < 0.82


def test_extracts_z370_aorus_gaming_5():
    from src.model_identification import canonical_listing_model
    assert canonical_listing_model('Gigabyte Z370 AORUS Gaming 5 ATX Motherboard') == 'GIGABYTE Z370 AORUS GAMING 5'
