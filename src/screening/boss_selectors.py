from __future__ import annotations

import os
from dataclasses import dataclass


def _selector_tuple(env_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(env_name)
    if not raw:
        return default
    items = tuple(part.strip() for part in raw.split("||") if part.strip())
    return items or default


@dataclass(frozen=True, slots=True)
class BossSelectors:
    search_url: str
    search_keyword_input: tuple[str, ...]
    search_city_input: tuple[str, ...]
    search_submit: tuple[str, ...]
    sort_active: tuple[str, ...]
    sort_recent: tuple[str, ...]
    list_ready: tuple[str, ...]
    candidate_card: tuple[str, ...]
    candidate_name: tuple[str, ...]
    candidate_title: tuple[str, ...]
    candidate_company: tuple[str, ...]
    candidate_experience: tuple[str, ...]
    candidate_education: tuple[str, ...]
    candidate_location: tuple[str, ...]
    candidate_active_time: tuple[str, ...]
    candidate_link: tuple[str, ...]
    candidate_external_id: tuple[str, ...]
    detail_ready: tuple[str, ...]
    detail_main_text: tuple[str, ...]
    next_page: tuple[str, ...]
    search_frame_name: str = "searchFrame"
    search_frame_url_contains: str = "/web/frame/search/"
    recommend_url: str = "https://www.zhipin.com/web/chat/recommend"
    recommend_list_ready: tuple[str, ...] = (
        ".candidate-recommend",
        ".recommend-list-wrap",
        ".card-list",
        ".card-item",
        ".candidate-card-wrap",
        ".card-inner",
        ".geek-list-wrap",
        ".recommend-list",
        "li.geek-info-card",
        "div.card-list",
        "a[ka*='open_resume']",
    )
    recommend_candidate_card: tuple[str, ...] = (
        ".card-list .card-item",
        ".card-item",
        ".candidate-card-wrap",
        ".card-inner.common-wrap",
        ".card-inner",
        "li.geek-info-card",
        ".geek-list-wrap li.geek-info-card",
        ".recommend-list li",
        "div.card-inner",
    )
    recommend_candidate_name_link: tuple[str, ...] = (
        ".candidate-head .name",
        ".candidate-head",
        ".card-inner",
        ".name-label",
        "a[ka*='open_resume']",
        "a[class*='name']",
        "a",
    )
    recommend_candidate_external_id: tuple[str, ...] = (
        "a[ka*='open_resume']",
        "li.geek-info-card",
        "[data-expect]",
        "[data-geek-id]",
        "[data-id]",
        "[data-uid]",
        "[data-jid]",
    )
    recommend_detail_ready: tuple[str, ...] = (
        ".card-inner",
        ".candidate-card-wrap",
        ".iboss-left",
        "div.resume-detail-wrap",
        "div.geek-resume-wrap",
        "div.card-content",
        "button:has-text('打招呼')",
    )
    recommend_download_button: tuple[str, ...] = (
        "button:has-text('下载')",
        "a:has-text('下载')",
        "button:has-text('简历')",
        "a:has-text('简历')",
    )
    recommend_greet_button: tuple[str, ...] = (
        ".button-list button:has-text('打招呼')",
        ".card-inner button:has-text('打招呼')",
        "button:has-text('打招呼')",
        "a:has-text('打招呼')",
        "[ka*='greet']",
    )
    recommend_close_button: tuple[str, ...] = (
        "div.dialog-wrap.active i.icon-close",
        "div.dialog-wrap.active .close",
        "div[data-type='boss-dialog'].active i.icon-close",
        "div[data-type='boss-dialog'].active .close",
        "div[role='dialog'] [aria-label*='关闭']",
    )
    recommend_frame_name: str = "recommendFrame"
    recommend_frame_url_contains: str = "/web/frame/recommend/"


def load_boss_selectors() -> BossSelectors:
    return BossSelectors(
        search_url=os.getenv("SCREENING_BOSS_SEARCH_URL", "https://www.zhipin.com/web/chat/search"),
        search_keyword_input=_selector_tuple(
            "SCREENING_BOSS_SEARCH_KEYWORD_SELECTORS",
            (
                "input.search-input",
                ".search-input-wrap input.search-input",
                "input[placeholder*='职位']",
                "input[placeholder*='搜索']",
                "input[name='query']",
                "input[type='search']",
            ),
        ),
        search_city_input=_selector_tuple(
            "SCREENING_BOSS_SEARCH_CITY_SELECTORS",
            (
                ".city-wrap input[type='text']",
                ".search-city-kw input[type='text']",
                "input[placeholder*='城市']",
                "input[name='city']",
                "input.city-input",
            ),
        ),
        search_submit=_selector_tuple(
            "SCREENING_BOSS_SEARCH_SUBMIT_SELECTORS",
            (
                ".search-input-wrap button",
                "button[type='submit']",
                "button.search-btn",
                "button[ka='search_btn']",
            ),
        ),
        sort_active=_selector_tuple(
            "SCREENING_BOSS_SORT_ACTIVE_SELECTORS",
            (
                ".my-list-sort .search-label:nth-child(2)",
                "[data-sort='active']",
                "button[ka='active_sort']",
            ),
        ),
        sort_recent=_selector_tuple(
            "SCREENING_BOSS_SORT_RECENT_SELECTORS",
            (
                ".my-list-sort .search-label:nth-child(1)",
                "[data-sort='recent']",
                "button[ka='recent_sort']",
            ),
        ),
        list_ready=_selector_tuple(
            "SCREENING_BOSS_LIST_READY_SELECTORS",
            (
                ".geek-list-wrap",
                ".card-list",
                "li.geek-info-card",
                "ul.rec-job-list",
                "div.recommend-list",
                "div.search-job-result",
                "div.job-list-box",
                "body",
            ),
        ),
        candidate_card=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_CARD_SELECTORS",
            (
                "li.geek-info-card",
                ".geek-list-wrap li.geek-info-card",
                "li.rec-job-list-item",
                "div.card-inner",
                "li.geek-item",
                "div.geek-card",
                "div.job-card-wrapper",
            ),
        ),
        candidate_name=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_NAME_SELECTORS",
            (".name-label", "span.name", "div.name", "h3.name", "div.geek-name", "span.geek-name"),
        ),
        candidate_title=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_TITLE_SELECTORS",
            (".work-exp-item .company-position", ".work-exp-item .position", "span.job-name", "div.job-title", "span.position-name", "span.expect-position"),
        ),
        candidate_company=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_COMPANY_SELECTORS",
            (".work-exp-item .company-name", "div.company-name", "span.company-name", "div.brand-name", "span.last-company"),
        ),
        candidate_experience=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_EXPERIENCE_SELECTORS",
            (".info-labels .label-text", "span.experience", "li.experience", "span.year", "span.geek-work-year"),
        ),
        candidate_education=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_EDUCATION_SELECTORS",
            (".info-labels .label-text", "span.degree", "li.degree", "span.edu", "span.geek-degree"),
        ),
        candidate_location=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_LOCATION_SELECTORS",
            (".expect-exp-box .render-two", "span.location", "span.city", "div.city", "span.geek-city"),
        ),
        candidate_active_time=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_ACTIVE_SELECTORS",
            (".active-desc-text", "span.active-time", "span.time", "div.active-time", "span.geek-active-time"),
        ),
        candidate_link=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_LINK_SELECTORS",
            ('a[ka="search_click_open_resume"]', "a",),
        ),
        candidate_external_id=_selector_tuple(
            "SCREENING_BOSS_CANDIDATE_ID_SELECTORS",
            ('a[ka="search_click_open_resume"]', "li.geek-info-card", "[data-geek-id]", "[data-id]", "[data-uid]"),
        ),
        detail_ready=_selector_tuple(
            "SCREENING_BOSS_DETAIL_READY_SELECTORS",
            (
                ".iboss-left",
                "div.resume-detail-wrap",
                "div.geek-resume-wrap",
                "div.resume-content",
                "div.card-content",
                "body",
            ),
        ),
        detail_main_text=_selector_tuple(
            "SCREENING_BOSS_DETAIL_TEXT_SELECTORS",
            (
                ".dialog-wrap.active .iboss-left",
                ".dialog-wrap.active .geek-resume-wrap",
                ".dialog-wrap.active .resume-content",
                ".iboss-left",
                "div.geek-resume-wrap",
                "div.resume-content",
            ),
        ),
        next_page=_selector_tuple(
            "SCREENING_BOSS_NEXT_PAGE_SELECTORS",
            (
                ".options-pages .next",
                ".options-pages a",
                "a.next",
                "button.next",
                "li.next > a",
                "[aria-label='Next Page']",
            ),
        ),
        search_frame_name=os.getenv("SCREENING_BOSS_SEARCH_FRAME_NAME", "searchFrame"),
        search_frame_url_contains=os.getenv("SCREENING_BOSS_SEARCH_FRAME_URL_CONTAINS", "/web/frame/search/"),
        recommend_url=os.getenv("SCREENING_BOSS_RECOMMEND_URL", "https://www.zhipin.com/web/chat/recommend"),
        recommend_list_ready=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_LIST_READY_SELECTORS",
            (
                ".candidate-recommend",
                ".recommend-list-wrap",
                ".card-list",
                ".card-item",
                ".candidate-card-wrap",
                ".card-inner",
                ".geek-list-wrap",
                ".recommend-list",
                "li.geek-info-card",
                "div.card-list",
                "a[ka*='open_resume']",
            ),
        ),
        recommend_candidate_card=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_CARD_SELECTORS",
            (
                ".card-list .card-item",
                ".card-item",
                ".candidate-card-wrap",
                ".card-inner.common-wrap",
                ".card-inner",
                "li.geek-info-card",
                ".geek-list-wrap li.geek-info-card",
                ".recommend-list li",
                "div.card-inner",
            ),
        ),
        recommend_candidate_name_link=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_NAME_LINK_SELECTORS",
            (
                ".candidate-head .name",
                ".candidate-head",
                ".card-inner",
                ".name-label",
                "a[ka*='open_resume']",
                "a[class*='name']",
                "a",
            ),
        ),
        recommend_candidate_external_id=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_ID_SELECTORS",
            (
                "a[ka*='open_resume']",
                "li.geek-info-card",
                "[data-expect]",
                "[data-geek-id]",
                "[data-id]",
                "[data-uid]",
                "[data-jid]",
            ),
        ),
        recommend_detail_ready=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_DETAIL_READY_SELECTORS",
            (
                ".card-inner",
                ".candidate-card-wrap",
                ".iboss-left",
                "div.resume-detail-wrap",
                "div.geek-resume-wrap",
                "div.card-content",
                "button:has-text('打招呼')",
            ),
        ),
        recommend_download_button=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_DOWNLOAD_SELECTORS",
            (
                "button:has-text('下载')",
                "a:has-text('下载')",
                "button:has-text('简历')",
                "a:has-text('简历')",
            ),
        ),
        recommend_greet_button=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_GREET_SELECTORS",
            (
                ".button-list button:has-text('打招呼')",
                ".card-inner button:has-text('打招呼')",
                "button:has-text('打招呼')",
                "a:has-text('打招呼')",
                "[ka*='greet']",
            ),
        ),
        recommend_close_button=_selector_tuple(
            "SCREENING_BOSS_RECOMMEND_CLOSE_SELECTORS",
            (
                "div.dialog-wrap.active i.icon-close",
                "div.dialog-wrap.active .close",
                "div[data-type='boss-dialog'].active i.icon-close",
                "div[data-type='boss-dialog'].active .close",
                "div[role='dialog'] [aria-label*='关闭']",
            ),
        ),
        recommend_frame_name=os.getenv("SCREENING_BOSS_RECOMMEND_FRAME_NAME", "recommendFrame"),
        recommend_frame_url_contains=os.getenv("SCREENING_BOSS_RECOMMEND_FRAME_URL_CONTAINS", "/web/frame/recommend/"),
    )
