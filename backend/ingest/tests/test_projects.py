from ingest.projects import canonical_key, match_project, summarize

LINKS = [
    ("2026-10-15T07:00:00Z", "White BORAH"),
    ("2026-10-15T08:00:00Z", "whiteBORAG"),
    ("2026-10-15T09:00:00Z", "whiteBORAG"),
]


def test_canonical_key():
    assert canonical_key("whiteBORAG") == "whiteborag"
    assert canonical_key("White BORAH") == "whiteborah"


def test_misread_joins():
    assert match_project("White BORAH", {"whiteborag": ["whiteBORAG"]}) == "whiteborag"


def test_case_variant_joins():
    assert match_project("whiteboRAG", {"whiteborag": []}) == "whiteborag"


def test_alias_matches():
    assert match_project("whitebora", {"x": ["whiteborah"]}) == "x"


def test_new_project():
    assert match_project("tender crawler", {"whiteborag": ["whiteBORAG"]}) is None


def test_display_name_vote():
    aliases, display = summarize(LINKS, None)
    assert aliases == {"White BORAH": 1, "whiteBORAG": 2}
    assert display == "whiteBORAG"


def test_display_tie_goes_to_latest():
    links = [("2026-10-15T09:00:00Z", "whiteBORAG"), ("2026-10-15T07:00:00Z", "White BORAH")]
    assert summarize(links, None)[1] == "whiteBORAG"
    links = [("2026-10-15T07:00:00Z", "whiteBORAG"), ("2026-10-15T09:00:00Z", "White BORAH")]
    assert summarize(links, None)[1] == "White BORAH"


def test_pinned_wins():
    assert summarize(LINKS, "WhiteBorag")[1] == "WhiteBorag"
