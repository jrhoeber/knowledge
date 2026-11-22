This repo will be a native iOS app. The app will be a general knowledge quiz app that helps people stay sharp on general knowledge topics. 
Topics will include
1. Mental Math (addition, subtraction, multiplication, division)
2. Geography (names of countries based on map or flag)
3. Vocabulary (word definitions)
4. Spelling (word is played and user is prompted for spelling, built in spellcheck disabled)
5. History (important events, key figures)
6. Everyday Science ("Why…?"): Why is the sea salty, how do rainbows form, why does ice float. This is the category most likely to come up with your daughter, and the one parents most often can't answer.
7. Space, Earth and Weather: Planets, moon phases, seasons, volcanoes, how clouds and wind work. Kids ask about these constantly, and they help with news about climate and storms.
8. Human Body and Health: Organs, how vaccines work, nutrition basics, how to read a medicine label. This covers the health literacy gap and kids' "why does my tummy growl" questions.
9. Animals and Nature: Habitats, food chains, which animals are mammals, how plants make food. Young kids are fascinated by these, and they tie into school science.
10. Money and Personal Finance: Interest, inflation, budgeting, insurance and risk. For your daughter, there's a kid-level version: saving, needs vs. wants, what a bank does. This is where adults score worst.
11. Civics and Government: Branches of government, how a bill becomes law, rights, how elections work. This is essential for following the news, and it's a common school topic.
12. Estimation and Everyday Numbers: Percentages, tips, unit conversions, and "about how many…" questions. This builds on Mental Math, and a slider for the answer would suit it better than multiple choice.
13. Idioms, Myths and Literary References: What "Achilles' heel," "Pandora's box" or "a Pyrrhic victory" mean, plus famous characters and fables. These come up constantly in reading, and the baseball study shows why that background matters.
14. Word Roots: Greek and Latin prefixes and roots ("bio," "graph," "-ology").
15. How Things Work (Technology): How the internet, planes, electricity and phones work. These came up on the list of questions that stump parents.
16. Economics in the News: GDP, tariffs, interest rates, the stock market. You could fold this into the Money category.
17. Arts and Music Basics: Famous artists and composers, instrument families. This rounds out general knowledge.
18. Philosophy: important figures, schools of thought, etc.


Technical architecture
1. Frontend: Native iOS (swift). Latest stable versions for all required dependencies. 
2. Backend: no backend to start. All needed info included in the app download, all information stored locally. 

User experience architecture
1. Onboarding: No log in or permissions required. User is prompted to select topics they want to be asked about. Once topics are selected the use should be thrown right into questions
2. Questions: Most questions should be multiple choice format with 4 options and only one right answer. Other formats are acceptable when needed. Questions and options should be spaced and sized such that they're easy to read any interact with
3. Menu: There should be a menu with 2 options: Topics & profile
4. Topics page: Allow users to enable or disable available topics
5. Profile: Show proficiency across topics. Proficiency defined in questions algorithm below. 

User experience style
1. Bright, inviting, modern. Bright background, pops of color.
2. Do not use emojis or other AI-esque design tells
3. Follow material design best practices
4. Do not use FABs anywhere for any reason
5. Leverage native iOS components

Question algorithm
1. All questions should have a difficulty score from 1-5 (5 is most difficult). 
2. Initially, Questions should be shown pseudo-randomly based on the topic a user has enabled. Question topics should be shown fairly evenly. For example, if 3 topics are enabled and the user answers 30 questions, each topic should have had roughly 10 questions each. Doesn't need to be exact, but shouldn't be completely random in a way that allows 5 questions in a row in the same topic if multiple topics are enabled.
3. Use spaced repetition, bringing missed questions back more often.
4. Adjust difficulty automatically based on proficiency. If a user answers a high % of easy questions in a topic correctly, the difficulty should become harder. Questions asked should still include all difficulty levels, but frequency should be weighted by how proficient a user is in the topic. For example, if a user consistently answers easy questions correctly, hard questions incorrectly, and medium questions inconsistently, the user should be asked more medium difficulty questions than easy or hard difficulty. A users proficiency should be expressed as a 1-10 number so the user can see their proficiency per topic. Proficiency should not be calculated for a topic until 10 questions are answered for a topic. Before proficiency is available for a topic, the user should be presented with a random assortment of question difficulty for the topic. 

Initial todo items
1. Create the base repo with a readme, claude.md, and basic iOS app structure.
2. Create a TODO.md that includes a list of the remaining 16 topics that are to be implemented.  
3. Start with only Mental Math and Vocabulary topics to start. Other topics will come later. Mental math should have at least 10,000 unique questions. Vocabulary should cover 40,000 base words. The words should be selected roughly based on the 40,000 most commonly used words in written english. Words with multiple definitions should include all common definitions in the answer set. If a word has multiple definitions, only one of the definitions should be presented in the multiple choice. All mental math and vocab questions should be multiple choice with 4 options and only one right answer.
4. Run the app using a simulator and iteratively improve the UX and test functionality to ensure everything is working properly. 
