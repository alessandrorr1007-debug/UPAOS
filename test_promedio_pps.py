import unittest
from services.banner_sso_service import banner_sso_service

class TestPromedioPonderado(unittest.TestCase):

    def test_calcular_pps_ejemplo_real_redondeado(self):
        """
        Prueba con los datos reales (cada nota redondeada a entero, >= .5 sube):
        - Infraestructura Como Codigo: 10.66 -> 11 * 4 = 44
        - Intel Art, Princip y Tecnic: 16.16 -> 16 * 4 = 64
        - Aplicac Moviles para Negocios: 11.06 -> 11 * 4 = 44
        - Deontologia Profesional: 15.4 -> 15 * 2 = 30
        - Metodolog Investigac Cientif: 14.9 -> 15 * 3 = 45
        - Agile Development: 9.84 -> 10 * 4 = 40
        Suma ponderada: 267 / 21 créditos = 12.7142857...
        Con round(..., 4) da 12.7143.
        """
        cursos = [
            {"crn": "5592", "nombre": "Infraestructura Como Codigo", "nota": 10.66, "creditos": 4},
            {"crn": "5598", "nombre": "Intel Art, Princip y Tecnic", "nota": 16.16, "creditos": 4},
            {"crn": "5636", "nombre": "Aplicac Moviles para Negocios", "nota": 11.06, "creditos": 4},
            {"crn": "6645", "nombre": "Deontologia Profesional", "nota": 15.4, "creditos": 2},
            {"crn": "3233", "nombre": "Metodolog Investigac Cientif", "nota": 14.9, "creditos": 3},
            {"crn": "5585", "nombre": "Agile Development", "nota": 9.84, "creditos": 4}
        ]

        pps = banner_sso_service.calcular_pps(cursos)
        self.assertIsNotNone(pps)
        self.assertEqual(pps, 12.7143)
        self.assertEqual(round(pps, 2), 12.71)

    def test_calcular_pps_redondea_media_arriba(self):
        """
        Notas con .5 deben redondear hacia arriba (criterio académico UPAO):
        - 9.5 -> 10 * 1 = 10
        - 10.5 -> 11 * 1 = 11
        Suma ponderada: 21 / 2 créditos = 10.5
        """
        cursos = [
            {"crn": "1111", "nombre": "Curso A", "nota": 9.5, "creditos": 1},
            {"crn": "2222", "nombre": "Curso B", "nota": 10.5, "creditos": 1}
        ]

        pps = banner_sso_service.calcular_pps(cursos)
        self.assertIsNotNone(pps)
        self.assertEqual(pps, 10.5)

    def test_calcular_pps_ignora_curso_sin_creditos(self):
        """
        Un curso sin créditos se excluye del PPS; con las notas restantes
        redondeadas a entero: 14.9 -> 15 * 3 = 45 / 3 = 15.0
        """
        cursos = [
            {"crn": "3233", "nombre": "Metodolog Investigac Cientif", "nota": 14.9, "creditos": 3},
            {"crn": "9999", "nombre": "Curso Desconocido", "nota": 15.0, "creditos": None}
        ]

        pps = banner_sso_service.calcular_pps(cursos)
        self.assertIsNotNone(pps)
        self.assertEqual(pps, 15.0)

    def test_combinar_notas_creditos(self):
        notas = [
            {"crn": "5592", "nombre": "Infraestructura Como Codigo", "nota": 10.66},
            {"crn": "9999", "nombre": "Curso Desconocido", "nota": 15.0}
        ]
        horario = [
            {"crn": "5592", "nombre": "Infraestructura Como Codigo", "creditos": 4}
        ]

        combinados = banner_sso_service.combinar_notas_creditos(notas, horario)
        self.assertEqual(len(combinados), 2)
        self.assertEqual(combinados[0]["creditos"], 4)
        self.assertIsNone(combinados[1]["creditos"])

if __name__ == "__main__":
    unittest.main()
