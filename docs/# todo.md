# todo

- detector + recovery з broad search
- прибрати стиснене читання
- коли робиш дослідження і встановлюєш щось що може знадобитися для результату - зберегт через теги пам'яті
- треба в сист промпті сказати що треба сейвити в дошку пам'яті важливі шляхи. exact file paths already located , exact symbols/method locations
- в іструкція пошуку написати що перед пошуком перевірити може те що хочеш знайти вже є в дошці пам'яті
- перевіряти коректність використання попередніх дошок пам'яті
- якщо в current/session memory already є exact verified file path, агент не має права шукати
    альтернативний path для того ж target без явного contradicting tool result.
- як відповідати на застарівання записів в дошці пам'яті
- не зберігати інтент в системному промпті. тільки в дошці пам'яті
- видимість дошки пам'яті і дошки активного інтенту, і дошки планування
- рушій планування використовувати. довгий інтент - треба планування

не видаляти теги шляхів довше
можливо рішення приймаит в блоках думання шодо тегів також

Тобто lifecycle clean, але evidence governance ще недостатнє.

***

P1. malformed_action recovery має бути strategy-aware

Поточний recovery каже “дай валідний JSON”. Для великого create_file треба:

Your action JSON failed to parse, likely because the content string is too large or contains unescaped nested code.
Do not repeat the same huge create_file JSON.
Use a smaller file, chunked write, or run_shell heredoc. << дай запит агенту кодування

***

після першого редагування файлу його зміст в історії якщо зберігається повному стані має оновлюватися бо модель використовує його для повторних читань. 

шляхи того що раз редагували чи досліджували - в дошку пам'яті як <path>my path</path>. але не більше 40 записів

DAY TASK < 5 DAY FOCUSSES

кращий віджет системних помилок

***

Що зламалось / головний дефект
P0: accepted intent + malformed think + action = action discarded

У step 6 агент нарешті видав валідний top-level intent, але зробив це всередині незакритого <think>. Runtime:

застосував intent;
побачив malformed_incomplete_think;
не dispatch-нув list_directory;
перейшов у recovery під уже активним INVESTIGATE intent.

Це дуже важливий edge case.

Формально runtime діє безпечно: action не виконується, бо response malformed. Але виникає частково застосований transaction:

intent committed;
action rejected;
model тепер у новому active contract;
користувач не отримав прогресу;
наступний крок залежить від recovery.

Це transactional atomicity bug / design smell.

Якщо response bundle невалідний через malformed control text, runtime не має частково commit-ити intent transition, якщо follow-up action у тому ж bundle не може бути dispatched.

***

 ▎  2. Централізація управління станом:                                                                               
 ▎                                                                                                                    
 ▎   • Проблема: Логіка використовує як об'єкт LoopContext, що передається між методами, так і глобальний стан        
 ▎     self.state та agent. Це може призводити до помилок та ускладнює відстеження потоку даних.                      
 ▎   • Рішення: Потрібно централізувати керування станом. Можна розширити LoopContext або створити окремий            
 ▎     клас-сховище стану, який би був єдиним джерелом правди для одного циклу обробки запиту. Це зробить потік       
 ▎     даних більш явним та передбачуваним.                                                                           
 ▎                                            