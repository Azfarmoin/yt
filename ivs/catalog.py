"""Curated, human-selected references. Only REFERENCES live here; all Quran/Hadith text is read from the pinned
source and verified at run time. `expect` guards against wrong references (the English text must contain it)."""

QURAN = [
    # (surah, from, to, theme, hook, expect_in_english)
    (94, 5, 6, "hardship and ease", "Struggling right now? Hear this.", "relief"),
    (2, 153, 153, "patience", "The two things Allah tells us to turn to.", "patient"),
    (14, 7, 7, "gratitude", "A promise about gratitude.", "grateful"),
    (13, 28, 28, "peace of heart", "Where do hearts find rest?", "remembrance"),
    (39, 53, 53, "repentance and hope", "Never lose hope in Allah's mercy.", "Mercy"),
    (65, 3, 3, "trust in Allah", "On trusting Allah.", "trust"),
    (3, 139, 139, "resilience", "When you feel low.", "despair"),
    (49, 13, 13, "human equality", "What really makes one person better than another?", "nations and tribes"),
    (93, 3, 3, "reassurance", "When you feel alone.", "forsaken"),
    (103, 1, 3, "time and faith", "Why time matters.", "loss"),
    (112, 1, 4, "tawhid", "Surah Al-Ikhlas.", "One"),
    (2, 152, 152, "remembrance of Allah", "A beautiful exchange with Allah.", "Remember"),
    (25, 63, 63, "good character", "How the servants of the Most Merciful walk.", "humility"),
    (24, 22, 22, "forgiveness", "Forgive, and be forgiven.", "forgive"),
    (20, 25, 28, "dua of Musa", "A dua for confidence and ease.", "breast"),
    (2, 201, 201, "dua", "A short dua for both worlds.", "good in this world"),
    (3, 8, 8, "dua for steadfastness", "A dua for a steady heart.", "hearts"),
    (2, 45, 45, "patience and prayer", "Seek help through this.", "perseverance"),
    (2, 186, 186, "closeness of Allah", "Is Allah close?", "close"),
    (40, 60, 60, "dua", "Allah invites you to ask.", "Call on Me"),
]

HADITH = [
    {
        "collection": "bukhari", "number": 6018, "theme": "good manners",
        "hook": "Three signs of a believer's character.",
        "ar_start": "مَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الآخِرِ فَلاَ",
        "ar_end": "أَوْ لِيَصْمُتْ",
        "en_start": "Anybody who", "en_end": "keep quiet.",
        "ur_start": "جو کوئی اللہ", "ur_end": "خاموش رہے۔",
        "expect_en": "neighbor",
        "book_ref": "Book 78, Hadith 49",
    },
]

# ---------------------------------------------------------------------------------------------------------------
# SCRIPTS: the editorial lines shown around the verse (context before, takeaway after).
# Rules: describe only what the text itself says; no tafsir claims, no invented history or quotations, no attribution of
# words to anyone. These are *editorial reflections*, labeled as such in the video description. They are written by the
# tool author, NOT by a scholar, so `reviewed` is False by default and items stay in `needs_review` until a person
# approves them (config script.require_review). Set reviewed=True only after a qualified person checked the lines.
# Each entry: (context_en, context_ur, takeaway_en, takeaway_ur)
# ---------------------------------------------------------------------------------------------------------------
SCRIPTS = {
    "quran:94:5-6": ("Allah repeats one promise twice in a row.", "اللہ تعالیٰ نے ایک ہی وعدہ لگاتار دو بار دہرایا ہے۔",
                     "Difficulty and ease come together. Keep going.", "مشکل کے ساتھ آسانی بھی ہوتی ہے۔ ہمت نہ ہاریں۔"),
    "quran:2:153": ("A direct instruction to the believers.", "اہلِ ایمان کو ایک سیدھی ہدایت۔",
                    "When things feel heavy, turn to patience and prayer.", "جب بوجھ بھاری لگے تو صبر اور نماز کا سہارا لیں۔"),
    "quran:14:7": ("Allah speaks about what gratitude brings.", "اللہ تعالیٰ شکر کے نتیجے کا ذکر فرماتے ہیں۔",
                   "Notice your blessings today and say Alhamdulillah.", "آج اپنی نعمتوں پر غور کریں اور الحمد للہ کہیں۔"),
    "quran:13:28": ("The ayah names the source of calm for believing hearts.", "آیت مومنوں کے دلوں کے سکون کا ذریعہ بتاتی ہے۔",
                    "Set aside a few minutes today to remember Allah.", "آج کچھ وقت اللہ کے ذکر کے لیے نکالیں۔"),
    "quran:39:53": ("A message addressed to people who have made mistakes.", "ان لوگوں سے خطاب جن سے غلطیاں ہوئی ہیں۔",
                    "Never delay turning back to Allah.", "اللہ کی طرف لوٹنے میں دیر نہ کریں۔"),
    "quran:65:3": ("A reminder about relying on Allah.", "اللہ پر بھروسے کی یاد دہانی۔",
                   "Do your part, then leave the rest to Allah.", "اپنی کوشش کریں، پھر باقی اللہ پر چھوڑ دیں۔"),
    "quran:3:139": ("Words of encouragement to the believers.", "اہلِ ایمان کو حوصلہ دینے والے الفاظ۔",
                    "Don't let a low moment make you lose heart.", "مشکل لمحات سے دل نہ چھوڑیں۔"),
    "quran:49:13": ("Allah addresses all of mankind, not one group.", "اللہ تعالیٰ تمام انسانوں سے مخاطب ہیں، کسی ایک گروہ سے نہیں۔",
                    "In this ayah, honour with Allah is measured by taqwa.", "اس آیت میں اللہ کے نزدیک عزت کا پیمانہ تقویٰ ہے۔"),
    "quran:93:3": ("A reassurance from Surah Ad-Duha.", "سورۃ الضحیٰ سے ایک تسلی۔",
                   "A reminder that Allah's care is never absent.", "یاد دہانی کہ اللہ کی نگہبانی کبھی ختم نہیں ہوتی۔"),
    "quran:103:1-3": ("A very short surah with a complete message.", "ایک بہت مختصر سورت جس میں مکمل پیغام ہے۔",
                      "Faith, good deeds, truth and patience are named as the way out of loss.", "ایمان، نیک عمل، حق اور صبر کو خسارے سے بچاؤ کا راستہ بتایا گیا ہے۔"),
    "quran:112:1-4": ("Surah Al-Ikhlas introduces Allah in four short ayat.", "سورۃ الاخلاص چار مختصر آیات میں اللہ کا تعارف کراتی ہے۔",
                      "Allah is One, the Self-Sufficient, and nothing is like Him.", "اللہ ایک ہے، بے نیاز ہے، اور اس جیسا کوئی نہیں۔"),
    "quran:2:152": ("An exchange between Allah and the one who remembers Him.", "اللہ اور اس کا ذکر کرنے والے کے درمیان ایک تعلق۔",
                    "Remember Allah, and be grateful.", "اللہ کو یاد کریں اور شکر ادا کریں۔"),
    "quran:25:63": ("A description of the servants of the Most Merciful.", "رحمٰن کے بندوں کا ایک وصف۔",
                    "Walk humbly, and answer harshness with peace.", "عاجزی سے چلیں اور سختی کا جواب سلامتی سے دیں۔"),
    "quran:24:22": ("An ayah about forgiving others.", "دوسروں کو معاف کرنے سے متعلق ایک آیت۔",
                    "Forgive, hoping that Allah forgives you.", "معاف کر دیں، اس امید پر کہ اللہ آپ کو معاف فرمائے۔"),
    "quran:20:25-28": ("The dua of Musa, peace be upon him, before a hard task.", "موسیٰ علیہ السلام کی دعا، ایک مشکل ذمہ داری سے پہلے۔",
                       "Before a big task, ask Allah to open your heart and ease your way.", "کسی بڑے کام سے پہلے اللہ سے دل کی کشادگی اور آسانی مانگیں۔"),
    "quran:2:201": ("A short and comprehensive dua.", "ایک مختصر اور جامع دعا۔",
                    "Ask Allah for good in both worlds.", "دونوں جہانوں کی بھلائی مانگیں۔"),
    "quran:3:8": ("A dua from Surah Ali 'Imran.", "سورۃ آل عمران کی ایک دعا۔",
                  "Ask Allah to keep your heart steady.", "اللہ سے دل کی ثابت قدمی مانگیں۔"),
    "quran:2:45": ("The ayah names two sources of help.", "آیت مدد کے دو ذرائع بتاتی ہے۔",
                   "Patience and prayer: use both.", "صبر اور نماز: دونوں سے مدد لیں۔"),
    "quran:2:186": ("Allah answers a question about Himself.", "اللہ تعالیٰ ایک سوال کا جواب عطا فرماتے ہیں۔",
                    "Allah is close and listens to every dua.", "اللہ قریب ہے اور ہر دعا سنتا ہے۔"),
    "quran:40:60": ("An invitation to make dua.", "دعا مانگنے کی دعوت۔",
                    "Ask Allah. He has promised to respond.", "اللہ سے مانگیں، اس نے جواب دینے کا وعدہ فرمایا ہے۔"),
    "hadith:bukhari:6018": ("Three actions tied to faith in Allah and the Last Day.", "اللہ اور آخرت پر ایمان سے جڑے تین اعمال۔",
                            "Today: be kind to your neighbour, honour your guest, and speak well.", "آج پڑوسی سے اچھا سلوک کریں، مہمان کی عزت کریں اور اچھی بات کہیں۔"),
}
SCRIPT_REVIEWED: set[str] = set()      # keys a qualified person has checked; add here after review

def script_for(key: str) -> dict | None:
    row = SCRIPTS.get(key)
    if not row:
        return None
    return {"context": {"en": row[0], "ur": row[1]}, "takeaway": {"en": row[2], "ur": row[3]},
            "reviewed": key in SCRIPT_REVIEWED, "author": "editorial (tool author), not a scholar"}
