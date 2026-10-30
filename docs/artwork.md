# Оформление Frontiers

Интерфейс использует локальные ресурсы: иллюстрации, текстуру дерева и SVG-значки.
Шрифты — системные Georgia и Segoe UI. Внешних загрузок для оформления нет.

У всех 94 карт каталога разные иллюстрации: 85 отдельных рисунков отрядов,
включая вторые формы и призываемые карты, пять особых/погодных PNG и четыре
погодные сцены из исходного атласа. Копии одной карты используют один рисунок.
Каждый из пятнадцати вариантов трёх лидеров также имеет собственный портрет.

Новые файлы: `src/frontiers/static/<ключ_карты>.png` и
`src/frontiers/static/leader_<ключ_лидера>.png`. Все созданы встроенным image_gen
через навык imagegen. Точные промпты 35 отрядов находятся в
`docs/card-art-prompts.json`, пяти вариантов Франциска — в
`docs/leader-art-prompts.json`. Назначение рисунка определяется ключом карты,
не её рядом или способностью; связь прописана в `static/artwork.css`, `static/shiron.css`
и `static/skone.css`. Для Широна промпты находятся в `docs/shiron-art-prompts.json`,
для Сконе — в `docs/skone-art-prompts.json`. Сконе получила 20 новых рисунков отрядов,
пять портретов Ульфрика и изображение Командного рога. Каждый ресурс сохранён в static.
Валькнут — собственный SVG-ресурс `static/valknut.svg`.
Иллюстрации Воительницы Яра (`ranger.png`) и Воительницы Сконе (`young_berserker.png`)
заменены отдельными портретами воительниц. Новые промпты и исходные файлы записаны
в `docs/skone-warrior-art-prompts.json`; верх портретов сохраняется в рамке карты.

`src/frontiers/static/card-art.png` — исходный атлас из 12 иллюстраций,
сетка 4 × 3. Для Мороза, Тумана, Шторма и Ясного неба сохранены четыре разные
сцены; другие фрагменты атласа больше не используются картами.
Ранее отложенные карты Сконе теперь доступны этой фракции и скрыты в редакторе Бургундии.
Их исходные изображения сохранены. В игровых колодах Бургундии доступно 35 карт.
У Пламенного странника, Аделины, Полкового хирурга, Ориана, Безымянного посла и
Ветерана и Капитана дорожной дружины изображение выровнено по верхнему краю: головы не обрезаются при
заполнении рамки в коллекции, руке и на столе.
`src/frontiers/static/wood.svg` и значки в `app.js` созданы в коде.

Промпт для генерации атласа:

```text
Use case: stylized-concept
Asset type: one production game-art sprite atlas for the original medieval card game FRONTIERS, 4 columns by 3 rows, 12 equally sized portrait panels, no gutters or margins, overall square image. Each panel has aspect ratio 3:4. The exact equal grid is critical for CSS sprite cropping. This is illustration art only, NOT a UI screenshot.
Primary request: richly painted original medieval Burgundian fantasy card illustrations, detailed oil painting / traditional fantasy book cover art, dramatic light, earthy browns, muted steel blue, wine red and antique gold. All subjects center-framed and readable when small, no typography, numbers, symbols, frames, borders or logos.
Panels left to right, top to bottom:
Row 1: a noble armored blue-cloaked knight with shield in autumn countryside; a hooded archer drawing a longbow in pine forest; a large wooden ballista at a stone fortress; a wise bearded crowned king in burgundy velvet and gold armor seated on his throne.
Row 2: a hooded spy holding parchment in a lantern-lit harbor; a female medieval field surgeon tending a soldier in a camp; a fierce fur-cloaked axeman in dark woodland; a powerful brown bear among mossy forest rocks.
Row 3: frost and snow covering a medieval mountain village; gray mist in a haunting ancient forest; a violent rainstorm over a coastal castle; warm sunlight over golden fields and a medieval hilltop town.
Constraints: twelve clean contiguous rectangular paintings in an exact 4x3 grid, consistent style, no duplicated panels, no modern items, no recognizable existing game characters, no interface. Full bleed art in each panel.
```

## Отдельные иллюстрации особых карт

Пять изображений созданы отдельными вызовами встроенного image_gen через навык imagegen.
Файлы в `src/frontiers/static/`: `decoy.png` (Чучело), `rain.png` (Ливень),
`scorch.png` (Казнь с черепом), `horn.png` (Штандарт), `mushroom.png` (Мухомор).
Они используются в коллекции, колоде, руке, на поле и в сбросе.
Шторм сохраняет прежнюю иллюстрацию из атласа и отличается от Ливня.
Портрет лидера отображается через SVG с фиксированным соотношением 3:4 и равномерным
масштабированием отдельного рисунка, без деформации лица. Медальоны рядов и значки
меча, лука и осадного орудия нарисованы в SVG/CSS. Лук показан по диагонали:
изогнутая дуга, оттянутая тетива и стрела. Карты на поле занимают высоту своего
ряда; иллюстрация заполняет карту, название видно только при просмотре сведений.
В руке также скрыты названия, иллюстрации занимают всю карту, а значки линии
и способностей увеличены. Названия сохранены в редакторе колоды и окне сведений.
Информация о ходе находится рядом с номером раунда. Кнопки паса и сдачи объединены;
приглашение доступно при подготовке колоды. Промежутки между рядами уменьшены,
отдельной полосы над полем нет.
В матче служебная панель размещена поверх боковых областей: ряды начинаются
от верхнего края окна, состояние соединения находится справа, а надпись
Frontiers возвращает на главную. Значения силы и значки класса/способностей на
столе масштабируются пропорционально ширине карты по образцу руки. Оформление
руки сохранено; пропорции пересчитываются при изменении окна и полном экране.

У каждой способности отрядов и героев есть отдельный значок:

| Способность | Значок |
| --- | --- |
| Шпион | Глаз |
| Лекарь | Крест |
| Сплочённость | Звенья цепи |
| Прилив сил | Стрелка вверх |
| Призыв | Три соратника |
| Знаменосец | Штандарт |
| Мухомор | Гриб |
| Берсерк | Угловатая голова медведя с оскалом, чёрный силуэт с прорезями глаз и клыков |
| Наследие | Призрак с сердитыми глазами и волнистым нижним краем |
| Казнь: ближний бой | Череп с мечом |
| Казнь: дальний бой | Череп с луком |
| Казнь: осада | Череп с осадным орудием |

У отрядов с двумя допустимыми рядами значок класса объединяет два различимых
силуэта: широкий меч внизу слева и натянутый лук со стрелой вверху справа.
В частности, такой значок имеет Габриэль фон Ард (ключ `herald`). Подсказка
на значке поясняет выбор между ближним и дальним боем.

Военная академия обозначается активным золотым штандартом в ячейке усиления
осадного ряда. По нажатию показывается описание. Если в ячейке уже лежит
штандарт, он остаётся единственным обозначением удвоения; эффекты не складываются.

### Чучело — decoy.png

```text
Use case: stylized-concept. Asset type: a single portrait illustration for an original medieval fantasy playing card in Frontiers. Full-bleed portrait composition, aspect ratio 3:4, richly detailed traditional oil painting, realistic materials, atmospheric dramatic light, muted medieval colors, matching a dark wooden card table with parchment and antique gold framing. Keep the main subject centered, large and immediately recognizable at thumbnail size; include a little breathing room around it. Image only, no text, lettering, numbers, card frame, logo, watermark, or UI. Subject: A handmade human-shaped medieval training scarecrow: straw head under a battered iron helmet, a weathered linen tunic stuffed with straw on a wooden crossbar, rope bindings and wooden pole, standing in an autumn military training yard. Clearly a straw dummy, not a person. Warm ochre sunlight, detailed worn straw and cloth, distant stone fortification.
```

### Ливень — rain.png

```text
Use case: stylized-concept. Asset type: a single portrait illustration for an original medieval fantasy playing card in Frontiers. Full-bleed portrait composition, aspect ratio 3:4, richly detailed traditional oil painting, realistic materials, atmospheric dramatic light, muted medieval colors, matching a dark wooden card table with parchment and antique gold framing. Keep the main subject centered, large and immediately recognizable at thumbnail size; include a little breathing room around it. Image only, no text, lettering, numbers, card frame, logo, watermark, or UI. Subject: Torrential rain over an abandoned medieval siege encampment, long dense diagonal sheets of rain, wet muddy ground and flooded ruts, an unmanned wooden siege machine in the background with a tarp, dark gray storm clouds. Water and rain are the unmistakable main subject. Desaturated blue-gray, cinematic realism. No sea, no ocean waves.
```

### Казнь — scorch.png

```text
Use case: stylized-concept. Asset type: a single portrait illustration for an original medieval fantasy playing card in Frontiers. Full-bleed portrait composition, aspect ratio 3:4, richly detailed traditional oil painting, realistic materials, atmospheric dramatic light, muted medieval colors, matching a dark wooden card table with parchment and antique gold framing. Keep the main subject centered, large and immediately recognizable at thumbnail size; include a little breathing room around it. Image only, no text, lettering, numbers, card frame, logo, watermark, or UI. Subject: A single large weathered human skull as a dramatic still-life, facing forward at a slight angle, unmistakable deep empty eye sockets and detailed teeth, resting on a dark stone surface with a few wisps of smoke and faint embers below. The skull dominates the center of the portrait. Strong chiaroscuro, bone ivory against charcoal black and muted warm brown. No living person, no gore.
```

### Штандарт — horn.png

```text
Use case: stylized-concept. Asset type: a single portrait illustration for an original medieval fantasy playing card in Frontiers. Full-bleed portrait composition, aspect ratio 3:4, richly detailed traditional oil painting, realistic materials, atmospheric dramatic light, muted medieval colors, matching a dark wooden card table with parchment and antique gold framing. Keep the main subject centered, large and immediately recognizable at thumbnail size; include a little breathing room around it. Image only, no text, lettering, numbers, card frame, logo, watermark, or UI. Subject: A magnificent upright medieval royal battle standard: rich deep blue cloth with an original embroidered golden fleur-de-lis, hanging from a gold-tipped crossbar on a wooden pole, its fabric fluttering in the wind. The standard is the central large subject, gold tassels and intricate textile visible, distant Burgundian hills and blurred tents in warm light. No soldier holding it, no text.
```

### Мухомор — mushroom.png

```text
Use case: stylized-concept. Asset type: a single portrait illustration for an original medieval fantasy playing card in Frontiers. Full-bleed portrait composition, aspect ratio 3:4, richly detailed traditional oil painting, realistic materials, atmospheric dramatic light, muted medieval colors, matching a dark wooden card table with parchment and antique gold framing. Keep the main subject centered, large and immediately recognizable at thumbnail size; include a little breathing room around it. Image only, no text, lettering, numbers, card frame, logo, watermark, or UI. Subject: A beautiful large red fly agaric mushroom with many white spots and a thick ivory stem, standing upright in moss, with one small fly agaric beside it. Close view from forest floor level, the red cap immediately recognizable. Detailed natural woodland painting, muted dark green moss and roots, soft golden light through the forest, red and ivory mushroom as main subject. No animal, no human.
```

