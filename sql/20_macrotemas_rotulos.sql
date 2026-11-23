-- Fase 8.5 - rotulos curados dos macrotemas e marcacao de topicos para revisao.
-- Valido para: python -m etl.macrotemas --k 30 --ligacao ward (seed 42). O UPDATE exige que o numero de
-- titulos de cada macrotema bata com o da rodada analisada; se algo divergir, ele nao altera a linha
-- (o SELECT final mostra quantas foram atualizadas: devem ser 30).
ALTER TABLE ml.macrotema ADD COLUMN IF NOT EXISTS rotulo_curado TEXT;
ALTER TABLE ml.topico    ADD COLUMN IF NOT EXISTS revisao TEXT;

UPDATE ml.macrotema m SET rotulo_curado = v.rotulo
FROM (VALUES
 (16, 18442, 'Educação e formação de professores'),
 (11, 13835, 'Clínica médica e fisiologia'),
 (3,  12675, 'Direito, política e ciências sociais'),
 (7,  11218, 'Agricultura familiar, rios e Amazônia'),
 (17,  9392, 'Artes, literatura e cultura'),
 (0,   9301, 'Física, energia e materiais'),
 (14,  9053, 'Educação, línguas e política (misto)'),
 (12,  8856, 'Botânica e fitotecnia'),
 (28,  8500, 'Café, bioenergia e alimentos'),
 (8,   8172, 'Saúde coletiva e enfermagem'),
 (13,  7027, 'Recursos hídricos, clima e geociências'),
 (1,   6935, 'Biologia celular, genética e microbiologia'),
 (4,   6908, 'Comunicação, tecnologia digital e esporte (misto)'),
 (18,  6617, 'Doenças infecciosas e pandemias'),
 (10,  6596, 'Educação inclusiva, linguagem e leitura'),
 (19,  6223, 'Odontologia, cirurgia e saúde bucal/ocular'),
 (2,   5763, 'Filosofia, religião e história'),
 (9,   5645, 'Violência, gênero e sexualidade'),
 (6,   5605, 'Saúde mental, drogas e psicologia'),
 (25,  5419, 'Cultura, história e relações étnico-raciais'),
 (5,   4669, 'Engenharia, robótica e redes'),
 (27,  4525, 'Medicina veterinária e animais'),
 (23,  4487, 'Nutrição e alimentação'),
 (21,  4185, 'Cidade, geografia e mobilidade'),
 (24,  3279, 'Envelhecimento, doenças neurodegenerativas e exercício'),
 (20,  3267, 'Ciências florestais'),
 (22,  3104, 'Ensino de ciências, química e biologia'),
 (26,  2243, 'Química e nanomateriais'),
 (15,  2103, 'Pesca e fauna marinha'),
 (29,  2065, 'Entomologia e controle biológico')
) AS v(id_macrotema, n_titulos, rotulo)
WHERE m.id_macrotema = v.id_macrotema AND m.n_titulos = v.n_titulos;

UPDATE ml.topico SET revisao = CASE id_topico
    WHEN 101 THEN 'ruído: palavras de uso geral'
    WHEN 100 THEN 'misto: assuntos médicos sem relação'
    WHEN 59  THEN 'misto: voz, audiovisual e audição'
    WHEN 155 THEN 'programa PET (educação), fora do tema animais'
    WHEN 245 THEN 'misto: música e termos de base de dados'
END
WHERE id_topico IN (101, 100, 59, 155, 245);

SELECT count(*) FILTER (WHERE rotulo_curado IS NOT NULL) AS macrotemas_com_rotulo_curado,
       count(*) AS macrotemas_total FROM ml.macrotema;
