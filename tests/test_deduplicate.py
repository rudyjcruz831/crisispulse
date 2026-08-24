from datetime import datetime

from pipelines.deduplicate import (
    display_headline_from_url,
    normalized_story_slug,
    story_group,
    title_like_path_segment,
)


def test_same_long_slug_in_same_window_groups_across_domains() -> None:
    first = "https://one.test/news/young-people-who-do-not-pass-gcse-english-and-maths"
    second = "https://two.test/2026/08/young-people-who-do-not-pass-gcse-english-and-maths.html"
    seen_at = datetime(2026, 8, 20, 14, 15)
    first_group = story_group(first, seen_at, "flood", "article-one")
    second_group = story_group(second, seen_at, "flood", "article-two")
    assert first_group == second_group
    assert first_group[1] == "url_slug_6h"


def test_short_generic_slug_falls_back_to_article_identity() -> None:
    assert normalized_story_slug("https://example.test/news/latest") is None
    group_id, method = story_group(
        "https://example.test/news/latest", datetime(2026, 8, 20, 14), "flood", "article-id"
    )
    assert group_id == "article-id"
    assert method == "canonical_url"


def test_trailing_numeric_article_id_uses_the_title_segment() -> None:
    url = (
        "https://one.test/article/astronomers-identify-new-type-of-black-hole-star-"
        "in-universe-while-hunting-space-mystery/73487469"
    )
    expected = (
        "astronomers-identify-new-type-of-black-hole-star-in-universe-while-hunting-"
        "space-mystery"
    )
    assert title_like_path_segment(url) == expected
    assert normalized_story_slug(url) == expected


def test_numeric_article_ids_group_syndicated_copies_by_title() -> None:
    first = "https://one.test/article/flash-flooding-disaster-assistance-minnesota/73487469"
    second = "https://two.test/article/flash-flooding-disaster-assistance-minnesota/73487469"
    seen_at = datetime(2026, 8, 20, 14, 15)
    assert story_group(first, seen_at, "flood", "one") == story_group(
        second, seen_at, "flood", "two"
    )


def test_display_headline_scans_past_trailing_dates_and_article_ids() -> None:
    assert display_headline_from_url(
        "https://www.rediff.com/news/report/uttarakhand-rains-swell-rivers-flood-streets/20260819.htm"
    ) == "Uttarakhand Rains Swell Rivers Flood Streets"
    assert display_headline_from_url(
        "https://timesofindia.indiatimes.com/city/ranchi/incessant-rain-inundates-kolhan-hundreds-of-houses-flooded-one-missing/articleshow/133349970.cms"
    ) == "Incessant Rain Inundates Kolhan Hundreds of Houses Flooded One Missing"
    assert display_headline_from_url(
        "https://www.local3news.com/local-news/update-whitfield-co-firefighters-put-new-rescue-boats-to-the-test/article_54bf1eb7-5a48-4209-9cad-341913dfe371.html"
    ) == "Update Whitfield Co Firefighters Put New Rescue Boats to the Test"


def test_display_headline_removes_embedded_dates_ids_and_punctuation() -> None:
    assert display_headline_from_url(
        "https://www.london-now.co.uk/news/national/26471089.heavy-rain-bring-threat-floods-another-hosepipe-ban-announced"
    ) == "Heavy Rain Bring Threat Floods Another Hosepipe Ban Announced"
    assert display_headline_from_url(
        "https://wtkg.iheart.com/content/2026-08-17-tropical-storm-lala-moves-on-after-hawaii-devastation"
    ) == "Tropical Storm Lala Moves on After Hawaii Devastation"
    assert display_headline_from_url(
        "https://aninews.in/news/national/general-news/over-53-lakh-jobs-delivered-1-crore-target-set-for-next-5-years-bihar-cm-samrat-choudhary20260821224832"
    ) == "Over 53 Lakh Jobs Delivered 1 Crore Target Set for Next 5 Years Bihar CM Samrat Choudhary"


def test_display_headline_rejects_routes_without_a_real_headline() -> None:
    assert display_headline_from_url("https://allafrica.com/stories/202608180433.html") is None
    assert display_headline_from_url("https://kajn.com/8-19-26") is None
    assert display_headline_from_url(
        "https://procurement-notices.undp.org/view_negotiation.cfm?nego_id=48864"
    ) is None
    assert display_headline_from_url(
        "https://taylorvilledailynews.com/local-news/srn-us-news/ac1e47550761973405c4a093205b8dcf"
    ) is None
    assert display_headline_from_url(
        "https://example.com/middle-east/article-906258"
    ) is None
