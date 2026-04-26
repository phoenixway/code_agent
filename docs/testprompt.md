app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchLinkOpener.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchModePreferences.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchResultCards.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchResultRendering.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchResultsSection.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchScreen.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchScreenComponents.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchScreenSheets.kt
app/src/main/java/com/romankozak/forwardappmobile/features/globalsearch/GlobalSearchViewModel.kt
app/src/main/java/com/romankozak/forwardappmobile/ui/dialogs/GlobalSearchDialog.kt

глобальний пошук екран. вид карток результатів. зліва зверху бейдж-іконка типу результату - прибрати.


там ще є аналогічний бейдж але з текстом справа внизу. накладається на рамку картки. ставити цей бейдж нормально під шляхом до контексту але над рамкою картки

***

 створи з нуля андроїд котлін компоуз рум додаток для закладок сайтів. робота така:
  - в будьякому додатку я роблю share with local-bookmark. саме сайт, url
  - в додатку в списку карток з'являється картка цього сайту. поля: тітл, url, adding datetime, user text comments,
  rating (0-5 stars)

***

зроби щоб теп по тегу на картці закладки додавало цей тег на поле фільтрації зверху і робило фільтрацію по цьому тегу закладок. зараз теп по чіпу тега ролбить те що робить теп по картці. 