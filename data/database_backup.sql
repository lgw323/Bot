BEGIN TRANSACTION;
CREATE TABLE "favorites" (user_id INTEGER, url TEXT, title TEXT, PRIMARY KEY(user_id, url));
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=BsLMyEFtqV8','Rescue Fire');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=mS41bHNw1WI','Max Verstappen Song');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=aW-lSN5QbF4','Oceano');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=B3wTGh1j4tw','Luna');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=Nxb2nM7oz0c','골판지 전사 OP (더빙판)');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=K3nl8O4tFMg','This is the Moment');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=aaxbZ1HS6-g','HEATS 2021');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=h1NrTdPDZ6s','긴급출동 레스큐 파이어 한국어 오프닝 (15화~29화) [TOMICA HERO RESCUE FIRE OPENING]');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=r3YNWOfRwIA','아쉬운상어페라리(MoeChakkaFerrari)');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=Cb0JZhdmjtg','IRIS OUT');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=GJMCi3NMyCQ','Working Class');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=M8GGg2b3H0k','Sacred War');
INSERT INTO "favorites" VALUES(415738789428723714,'https://www.youtube.com/watch?v=iU6mMLmaZhg','March Of The Defenders');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=uxPavPqtuGc','【魔法少女にあこがれて】第八話挿入歌「L・O・V・E・リーロコ♡」【曲・詩：ロコムジカ】');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=aaxbZ1HS6-g','HEATS 2021');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=vzM5Du4Eabg','헬다이버즈의 노래');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=PH4TZpQHMd8','How to become a cute anime girl');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=jKlL6wvGrbc','F1 Theme - Build Up & Starting Grid');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=EuCKE4gFmP4','Arknights OST - Battleplan Extinguished Sins「Lyric Video」- Martin Gonzalez & Elizabeth Hull');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=7ZccU9O47Q4','혹시민생회복소비쿠폰사용가능한가요');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=YhX_Woa3kVA','F1');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=m_6mVDi3UOs','【 ASMR House 】 だいあるのーと / 七草くりむ 【 Off Vocal 配布 】');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=r2ko422xW0w','지능이 떨어지는 브금');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=xPriebc1NJE','[미니의 쥬크박스] 08 - ALWAYS OPEN (FEAT. 인피니트) [유후미]');
INSERT INTO "favorites" VALUES(315064065783365632,'https://www.youtube.com/watch?v=LevPoT72rbw','Arknights OST - Battleplan Arclight | アークナイツ/明日方舟 危機契約 弧光 BGM');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=G5mbcsDvKo8','이찬혁 - 멸종위기사랑 [가사 | Lyrics]');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=8aROH2pWeJk','You''ve been Asaram''d (Full ver)');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=PH4TZpQHMd8','How to become a cute anime girl');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=98sUvgl6Q8Q','The Town Inside Me (Hanii remix) / Guilty Gear Strive');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=m_6mVDi3UOs','【 ASMR House 】 だいあるのーと / 七草くりむ 【 Off Vocal 配布 】');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=xvlrq-Q93eM','이선희 (Lee Sun Hee) - 여우비 (Fox Rain) [내 여자친구는 구미호 OST Part 1] 가사');
INSERT INTO "favorites" VALUES(281745554097176577,'https://www.youtube.com/watch?v=V0W8ITaMpII','[DJMAX] 매드니스 트로트 ver.');
CREATE TABLE music_play_counts (
                guild_id INTEGER,
                url TEXT,
                title TEXT,
                play_count INTEGER DEFAULT 1,
                PRIMARY KEY(guild_id, url)
            );
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=Nxb2nM7oz0c','골판지 전사 OP (더빙판)',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=r3YNWOfRwIA','아쉬운상어페라리(MoeChakkaFerrari)',3);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=zG7bjyIqQ1s','[Helldivers 2] 민주주의는 뽕짝으로 부터 (뽕짝 ver.)',5);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=DPYCaIbUz7A','BEYOND THE TIME (Mobius No Sora Wo Koete) -2025 Version-',3);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=Cb0JZhdmjtg','IRIS OUT',5);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=107UoVP2fAA','Heroine',3);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=R401j1QAvEg','スプリットダンス / 初音ミク・重音テト',4);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=GJMCi3NMyCQ','Working Class',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=BsLMyEFtqV8','Rescue Fire',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=h1NrTdPDZ6s','긴급출동 레스큐 파이어 한국어 오프닝 (15화~29화) [TOMICA HERO RESCUE FIRE OPENING]',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=QkF3oxziUI4','Led Zeppelin - Stairway To Heaven (Official Audio)',4);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=p2rmoi1caNY','Hyundai N | N Playlist — Nürburgring Eurobeat Dash',3);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=LevPoT72rbw','Arknights OST - Battleplan Arclight | アークナイツ/明日方舟 危機契約 弧光 BGM',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=NTrm_idbhUk','Kikuo - 愛して愛して愛して',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=9HEfp50sA2U','극장판 짱구는 못말려 12기 ED 동그라미를 주자 / 한일가사 / 고음질 [NO PLAN - ○(マル)あげよう]',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=6b1Qim1F1Yw','짱구는 못말려 극장판 5기: 암흑 마왕 대추적 엔딩',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=DduoqyK2CI0','가슴 시린 이야기 (Rap Feat. 용준형 of BEAST)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=O0z7yy2XGdU','With Me',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=6m1Hnl7-7Ms','Incomplete',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=1iTT2csCtYY','Insomnia (불면증)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=I8eIsqF0d1k','Over U',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=3AMi31_x3nQ','Luv Shine',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=4H2kOcouvMM','7 Days',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=682KQeYLrM0','Metal and Steel',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=JttJh13UaxA','RPG Maker VX Ace ~ Dungeon #1',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=B3wTGh1j4tw','Luna',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=BXsWn9DhF5g','Welcome To Jurassic Park',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=M9XPfymOx3Q','에릭사티 ''짐노페디'' 1번 (Erik Satie ''Gymnopedie No.1 Lent et douloureux'')',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=NtB3mwMmUfE','(한글 자막 / 가사) 길티기어 스트라이브 해피 케이오스 테마곡 - Drift',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=99FA0Zw9P1Q','너 임마 청년',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=5yLUVT2E3LE','Jingle Jangle Jingle (but full)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=DiiuanYFl2k','Jimmy Page & Robert Plant - Rock and Roll (Tokyo, 1996)',2);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=89dGC8de0CA','Aerosmith - Dream On (Audio)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=K6qj09OHvjw','Pink Floyd - Wish You Were Here (Official Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=CGj85pVzRJs','The Beatles - The Beatles - Let It Be (Official Music Video) [Remastered 2015]',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=PadKCVBIN94','Queen - Bohemian Rhapsody 1981 Live Video Full HD',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=OMOGaugKpzs','The Police - Every Breath You Take (Official Music Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=FTQbiNvZqaY','Toto - Africa (Official HD Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=1vrEljMfXYo','John Denver - Take Me Home, Country Roads (Official Audio)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=4-43lLKaqBQ','The Animals - House of the Rising Sun (1964) ♫ 60+ YEARS 🎶⭐ ❤',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=O4irXQhgMqg','The Rolling Stones - Paint It, Black (Official Lyric Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=KQetemT1sWc','The Beatles - The Beatles - Here Comes The Sun (Official Music Video) [2019 Mix]',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=NAEppFUWLfc','Simon & Garfunkel - The Sound of Silence (from The Concert in Central Park)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=6Ejga4kJUts','The Cranberries - Zombie (Official Music Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=DeumyOzKqgI','Adele - Skyfall (Official Lyric Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=Oextk-If8HQ','Keane - Somewhere Only We Know (Official Music Video)',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=2n5MGtzApxU','몬스터 헌터 와일즈 OST - 영웅의 증표',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=5KI80OCGOxM','【유희왕GX 더빙판】 난 지고 싶지 않아!',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=EuCKE4gFmP4','Arknights OST - Battleplan Extinguished Sins「Lyric Video」- Martin Gonzalez & Elizabeth Hull',1);
INSERT INTO "music_play_counts" VALUES(860135576224792617,'https://www.youtube.com/watch?v=171skzi5BKc','Queen - Made In Heaven (Official Lyric Video)',1);
CREATE TABLE music_settings (
                guild_id INTEGER PRIMARY KEY,
                volume REAL DEFAULT 1.0
            );
INSERT INTO "music_settings" VALUES(860135576224792617,1.0);
CREATE TABLE "users" (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_vc_seconds INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
INSERT INTO "users" VALUES(231782966127230976,860135576224792617,27937,43,4047);
INSERT INTO "users" VALUES(271259127584391168,860135576224792617,5005,14,0);
INSERT INTO "users" VALUES(404259657570582538,860135576224792617,8419,20,15772);
INSERT INTO "users" VALUES(428487165975068672,860135576224792617,5531,15,1374);
INSERT INTO "users" VALUES(429559300994629632,860135576224792617,2418,9,33972);
INSERT INTO "users" VALUES(682242502841204751,860135576224792617,754,4,0);
INSERT INTO "users" VALUES(765164086412574720,860135576224792617,703,4,0);
INSERT INTO "users" VALUES(281745554097176577,860135576224792617,55813,68,114489);
INSERT INTO "users" VALUES(415738789428723714,860135576224792617,14327,28,37958);
INSERT INTO "users" VALUES(315064065783365632,860135576224792617,30517,46,88183);
INSERT INTO "users" VALUES(415738789428723714,812141867898503188,2190,8,21991);
INSERT INTO "users" VALUES(280876747589681163,860135576224792617,876,5,0);
COMMIT;
