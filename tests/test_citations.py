"""Tricky citation formats found in real judgments (step 2). Run:  python -m pytest tests/ -q"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "citations"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraping"))

from collect_judgments import normalise_case_no
from extract_citations import extract_from_judgment, link, strip_running_headers


def cites(text, case_id="SC_APPEAL_1_2020", **kw):
    return extract_from_judgment(case_id, text, **kw)


def one(text, **kw):
    found = [c for c in cites(text, **kw) if c["kind"] != "supra"]
    assert len(found) == 1, [c["raw"] for c in found]
    return found[0]


# ---------------------------------------------------------------- law reports

def test_year_ranges_keep_first_year():
    c = one("In Perera v. Silva (1978/79) 2 SLR 65, it was held")
    assert (c["year"], c["report_key"], c["case_name"]) == ("1978", "SLR_1978_2_65", "Perera v. Silva")
    assert one("see [1978/79] 1 SLR 352 (SC)")["report_key"] == "SLR_1978_1_352"
    assert one("(1978-79) 1 Sri.L.R. 4 held")["report_key"] == "SLR_1978_1_4"


def test_scc_year_then_bracket():
    c = one("Kesavananda 1997 [1 SCC 388] held")
    assert (c["report_key"], c["year"], c["foreign"]) == ("SCC_1997_1_388", "1997", True)


def test_old_english_law_reports_series():
    c = one("Blackburn J in Taylor v Caldwell (1871) LR 6 QB 597 at 600")
    assert (c["report_key"], c["case_name"], c["foreign"]) == ("LR_QB_1871_6_597", "Taylor v Caldwell", True)
    assert one("Hochster v De la Tour (1875) LR 10 QB 111")["case_name"] == "Hochster v De la Tour"
    assert one("(1878) L. R. 8 Ch. D. 286")["report_key"] == "LR_ChD_1878_8_286"
    assert one("(1871) LR 3 PC 465")["report_key"] == "LR_PC_1871_3_465"


def test_sri_lr_without_volume():
    c = one("In Mendis v Perera [2003] Sri L.R. 270 it was")
    assert (c["report_key"], c["case_name"]) == ("SLR_2003_NA_270", "Mendis v Perera")


def test_case_name_directly_before_bracket():
    assert one("In Karunawathie v Wijesuria and Another[1980] 2 SLR 6 it was")["case_name"] == \
        "Karunawathie v Wijesuria and Another"


def test_english_report_without_volume_keeps_full_year():
    c = one("As held in Re Diplock [1949] Ch 333 the money")
    assert (c["reporter"], c["year"], c["volume"], c["page"]) == ("Ch", "1949", None, "333")
    assert c["report_key"] == "Ch_1949_NA_333"


def test_appeal_cases_without_volume():
    c = one("As observed by Lord Devlin in Hussein v. Chong Fook Kam [1970] AC 942 at 948,")
    assert (c["reporter"], c["year"], c["page"]) == ("AC", "1970", "942")
    assert c["case_name"] == "Hussein v. Chong Fook Kam"


def test_air_year_court_page():
    c = one("the Indian Supreme Court in Maneka Gandhi v Union of India AIR 1978 SC 597 held")
    assert c["report_key"] == "AIR_1978_SC_597" and c["year"] == "1978" and c["foreign"]
    c = one("see AIR 1981 SC 852.")
    assert c["report_key"] == "AIR_1981_SC_852"


def test_nlr_part_volume():
    c = one("Sharvananda in Caledonian Estates Ltd. vs. Hillman (1977) 79(i) NLR 421 stating that")
    assert (c["volume"], c["page"], c["year"]) == ("79(1)", "421", "1977")
    assert c["report_key"] == "NLR_79_421"                 # part-volume -> same key as "79 NLR 421"
    assert one("in X v Y 79 (II) N.L.R. 12")["report_key"] == "NLR_79_12"
    assert one("in X v Y 79 NLR 421")["report_key"] == "NLR_79_421"


def test_common_sri_lankan_forms():
    assert one("in A v B (2004) 1 Sri LR 12.")["report_key"] == "SLR_2004_1_12"
    assert one("in A v B [1997] 2 Sri L.R 98.")["report_key"] == "SLR_1997_2_98"
    assert one("Coconut Research Board v Fernando 1993 (1) S.L.R. 219")["report_key"] == "SLR_1993_1_219"
    assert one("Chelliah vs. Wijenathan 54 NLR 337")["report_key"] == "NLR_54_337"
    assert one("MOHAMADU vs. PATHUMAH [11 C.L.R. 48]")["reporter"] == "CLR"
    assert one("Dayawathie vs. Dias and others BALR [2013] Vol. XX 20 was")["report_key"] == "BLR_2013_20_20"
    assert one("Fowzie v Vehicles Lanka (Pvt) Ltd (2008) BLR 127 and")["report_key"] == "BLR_2008_NA_127"
    assert one("Jayalath, SI, and 6 others 2008 Part II B.L.R. 169, at")["report_key"] == "BLR_2008_2_169"


def test_bare_reporter_without_volume_or_year_is_ignored():
    assert cites("under section 12 of the NLR 45 something") == []


# ---------------------------------------------------------------- case numbers

def test_slash_case_number_with_sc_minutes_date():
    c = one("As I held in Wijesinghe v. Wickramaratne (SC/APPEAL/154/2017, SC Minutes of 21.11.2022): A party")
    assert c["case_no"] == "SC_APPEAL_154_2017"
    assert c["minutes_date"] == "2022-11-21"
    assert c["case_name"] == "Wijesinghe v. Wickramaratne"


def test_other_case_number_forms():
    assert one("in [SC/HCCA/LA/Case No. 279/2012; decided]")["case_no"] == "SC_HCCA_LA_279_2012"
    assert one("in SC (CHC) Appeal No. 36/2004 the court")["case_no"] == "SC_CHC_36_2004"
    assert one("(SC/TAB/4/2023, SC Minutes of 07.10.2024)")["case_no"] == "SC_TAB_4_2023"
    assert one("in SC (F/R) Application No. 405/2018 it was")["case_no"] == "SC_FR_405_2018"


def test_normalise_case_no_old_formats_unchanged():
    assert normalise_case_no("sc-fr-403-2016") == "SC_FR_403_2016"
    assert normalise_case_no("SC (FR) Application No. 256/2017") == "SC_FR_256_2017"
    assert normalise_case_no("scfr_542_09.pdf") == "SC_FR_542_2009"
    assert normalise_case_no("SC SPL LA 138/2019") == "SC_SPL_LA_138_2019"
    assert normalise_case_no("SC (SPL) LA No. 109/2018") == "SC_SPL_LA_109_2018"
    assert normalise_case_no("SC (HC) LA No.233/2010") == "SC_HC_LA_233_2010"


# ---------------------------------------------------------------- not citations

HEADER_JUDGMENT = "\n".join(
    ["IN THE SUPREME COURT OF THE DEMOCRATIC SOCIALIST REPUBLIC OF SRI LANKA",
     "SC APPEAL NO. 120/2021", "SC SPL LA 138/2019", "CA Case No. CA (TAX) 17/2017", "BEFORE: A, J."]
    + [line for k, body in enumerate(["The appellant filed action.", "The trial judge held for him.",
                                      "On appeal it was reversed.", "Leave was granted on two questions.",
                                      "We now consider them."], 1)
       for line in (f"[SC APPEAL 120/2021] Page {k} of 5", body)]
    + ["This court followed SC Appeal 45/2010 in this matter."]
)


def test_running_headers_are_removed():
    text, removed = strip_running_headers(HEADER_JUDGMENT, n_pages=5)
    assert removed == 5 and "Page 3 of 5" not in text and "On appeal it was reversed." in text


def test_own_number_caption_and_headers_are_not_citations():
    found = cites(HEADER_JUDGMENT, case_id="SC_APPEAL_120_2021", n_pages=5)
    assert [c["case_no"] for c in found] == ["SC_APPEAL_45_2010"]


def test_cases_heard_together_are_not_citations():
    text = "\n".join(
        ["SC FR Application No. 221/2021", "Petitioner", "BEFORE: X, J."]
        + [line for k in range(1, 7) for line in
           ("[SC FR 221/2021, SC FR 225/2021 and SC FR 228/2021]", f"Page {k} of 6", "Some facts" + "." * k)]
    )
    assert cites(text, case_id="SC_FR_221_2021", n_pages=6) == []


def test_own_number_ignored_for_unparsed_judgment():
    text = "SC Writ No. 03/2024 - Judgment 1\nBEFORE: X\nThis petition SC Writ No. 03/2024 is dismissed."
    assert cites(text, case_id="UNPARSED_37", case_no_raw="sc-writ-03-2024") == []


# ---------------------------------------------------------------- linking (the "Fernando" problem)

DB = {
    "SC_APPEAL_81_2009": {"parties": "Fernando and Others v. Fernando and Others", "year": 2010, "decided": "2010-05-01"},
    "SC_FR_246_2022": {"parties": "Saravanamuttu v. Attorney General and Others", "year": 2023, "decided": "2023-03-01"},
    "SC_APPEAL_154_2017": {"parties": "Wijesinghe v. Wickramaratne", "year": 2022, "decided": "2022-11-21"},
    "SC_APPEAL_1_2024": {"parties": "Citing v. Case", "year": 2025, "decided": "2025-01-01"},
}


def linked(text):
    cs = cites(text, case_id="SC_APPEAL_1_2024")
    link(cs, DB)
    return cs[0]


def test_old_nlr_case_never_links_to_a_2009_judgment():
    c = linked("Gunatilleke v Fernando (1921) 22 NLR 385")
    assert c["link_method"] == "report_key" and c["target"] == "NLR_22_385"


def test_one_shared_surname_is_not_enough():
    c = linked("Perera v. Fernando [2011] 1 Sri LR 10")
    assert c["link_method"] == "report_key"


def test_generic_same_surname_names_need_review():
    c = linked("Fernando v. Fernando [2011] 1 Sri LR 10")
    assert c["link_method"] == "needs_review" and c["candidate"] == "SC_APPEAL_81_2009"
    assert c["target"] == "SLR_2011_1_10"          # not accepted as a link


def test_both_parties_and_year_match():
    c = linked("Saravanamuttu v. AG [2023] 1 Sri LR 50")
    assert c["link_method"] == "name_fuzzy" and c["target"] == "SC_FR_246_2022"


def test_report_year_before_judgment_year_is_rejected():
    c = linked("Saravanamuttu v. Attorney General [2019] 1 Sri LR 50")
    assert c["link_method"] == "report_key"


def test_case_number_with_matching_minutes_date():
    c = linked("Wijesinghe v. Wickramaratne (SC/APPEAL/154/2017, SC Minutes of 21.11.2022)")
    assert (c["target"], c["link_method"]) == ("SC_APPEAL_154_2017", "case_number+date")


def test_case_number_with_different_minutes_date_needs_review():
    c = linked("Wijesinghe v. Wickramaratne (SC/APPEAL/154/2017, SC Minutes of 03.02.2019)")
    assert c["link_method"] == "needs_review" and c["candidate"] == "SC_APPEAL_154_2017"
