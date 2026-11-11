"""Famous sights with a weekly closing day, each read from its official page.

Used twice: the opening-days check looks here first, so the best-known traps
(the Louvre on a Tuesday) are caught without depending on a web search or on
how well a model reads a snippet; and the /closed-days page lists them.

Each entry was read from the linked official page in November 2026. Hours
change (holidays, seasons, renovations), so the page tells readers to follow
the source before they go. Keep this list short and sourced: one wrong line
here costs more than ten missing ones.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CHECKED_ON = "November 2026"


@dataclass(frozen=True)
class KnownSight:
    name: str
    city: str
    country: str  # ISO code, lower case
    closed: str  # as shown to people
    days: tuple[str, ...]  # weekdays closed all day (empty: no full-day closure)
    keys: tuple[str, ...]  # accent-free lower-case names it goes by
    source: str


SIGHTS = [
    KnownSight("Louvre Abu Dhabi", "Abu Dhabi", "ae", "Mondays", ("Monday",), ("louvre abu dhabi",),
               "https://www.louvreabudhabi.ae/en/visit/plan-your-visit/opening-times"),
    KnownSight("Louvre Museum", "Paris", "fr", "Tuesdays", ("Tuesday",), ("louvre",),
               "https://www.louvre.fr/en/visit/hours-admission"),
    KnownSight("Musée d'Orsay", "Paris", "fr", "Mondays", ("Monday",), ("musee d orsay", "orsay museum"),
               "https://www.musee-orsay.fr/en/visit"),
    KnownSight("Palace of Versailles", "Versailles", "fr", "Mondays", ("Monday",),
               ("palace of versailles", "chateau de versailles", "versailles palace"),
               "https://en.chateauversailles.fr/plan-your-visit/practical-information"),
    KnownSight("Vatican Museums", "Rome", "va", "Sundays, except the last Sunday of the month", ("Sunday",),
               ("vatican museums", "musei vaticani", "sistine chapel"),
               "https://www.museivaticani.va/content/museivaticani/en/info/orari-musei-vaticani.html"),
    KnownSight("Uffizi Gallery", "Florence", "it", "Mondays", ("Monday",), ("uffizi",),
               "https://www.uffizi.it/en/the-uffizi"),
    KnownSight("Museo Reina Sofía", "Madrid", "es", "Tuesdays", ("Tuesday",), ("reina sofia",),
               "https://www.museoreinasofia.es/en/visit/main-site/"),
    KnownSight("Topkapı Palace", "Istanbul", "tr", "Tuesdays", ("Tuesday",), ("topkapi",),
               "https://www.millisaraylar.gov.tr/Lokasyon/2/topkapi-sarayi"),
    KnownSight("Dolmabahçe Palace", "Istanbul", "tr", "Mondays", ("Monday",), ("dolmabahce",),
               "https://www.millisaraylar.gov.tr/Lokasyon/3/Dolmabahce-Sarayi"),
    KnownSight("Bardo National Museum", "Tunis", "tn", "Mondays", ("Monday",),
               ("bardo national museum", "bardo museum", "musee national du bardo", "musee du bardo"),
               "https://patrimoinedetunisie.com.tn/en/museums/the-national-bardo-museum"),
    KnownSight("Musée Yves Saint Laurent", "Marrakech", "ma", "Wednesdays", ("Wednesday",),
               ("yves saint laurent museum", "musee yves saint laurent", "ysl museum", "musee ysl"),
               "https://www.museeyslmarrakech.com/en/"),
    KnownSight("Sheikh Zayed Grand Mosque", "Abu Dhabi", "ae",
               "Friday late morning to mid-afternoon (visitors)", (), (),
               "https://www.szgmc.gov.ae/en/worshippers/en-v-visiting-hours"),
    KnownSight("Taj Mahal", "Agra", "in", "Fridays", ("Friday",), ("taj mahal",),
               "https://www.tajmahal.gov.in/"),
    KnownSight("Gyeongbokgung Palace", "Seoul", "kr", "Tuesdays", ("Tuesday",), ("gyeongbokgung",),
               "https://english.visitseoul.net/attractions/Gyeongbokgung/ENP000072"),
    KnownSight("Forbidden City (Palace Museum)", "Beijing", "cn", "Mondays, except public holidays",
               ("Monday",), ("forbidden city", "palace museum beijing"),
               "https://intl.dpm.org.cn/visit.html?l=en"),
    KnownSight("Tokyo National Museum", "Tokyo", "jp", "Mondays (Tuesday when Monday is a holiday)",
               ("Monday",), ("tokyo national museum",),
               "https://www.tnm.jp/modules/r_free_page/index.php?id=113&lang=en"),
    KnownSight("The Met Fifth Avenue", "New York", "us", "Wednesdays", ("Wednesday",),
               ("metropolitan museum of art", "the met fifth avenue", "met museum"),
               "https://www.metmuseum.org/plan-your-visit/met-fifth-avenue"),
]


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", text).strip()


def lookup(name: str, country_code: str = "") -> KnownSight | None:
    """The known sight ``name`` refers to, if it has a full-day closing day.

    ``country_code`` (when the place was found on the map) must match, so the
    Bardo museum in Algiers isn't given Tunis's closing day. Entries are in
    order of specificity: "Louvre Abu Dhabi" is tried before "Louvre".
    """
    folded = _fold(name)
    for sight in SIGHTS:
        if not sight.days or (country_code and country_code.lower() != sight.country):
            continue
        if any(re.search(rf"\b{re.escape(key)}\b", folded) for key in sight.keys):
            return sight
    return None
