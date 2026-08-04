import unittest
from services.banner_sso_service import banner_sso_service

class TestPromedioPonderado(unittest.TestCase):

    def test_calcular_pps_ejemplo_real_redondeado(self):
        """
        Prueba con los datos reales del prompt (notas redondeadas a 2 decimales):
        - Infraestructura Como Codigo: 10.66 * 4 = 42.64
        - Intel Art, Princip y Tecnic: 16.16 * 4 = 64.64
        - Aplicac Moviles para Negocios: 11.06 * 4 = 44.24
        - Deontologia Profesional: 15.4 * 2 = 30.80
        - Metodolog Investigac Cientif: 14.9 * 3 = 44.70
        - Agile Development: 9.84 * 4 = 39.36
        Suma ponderada: 266.38 / 21 créditos = 12.6847619...
        Con round(..., 4) da 12.6848 y con 2 decimales 12.68.
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
        self.assertEqual(round(pps, 2), 12.68)
        self.assertEqual(pps, 12.6848)

    def test_calcular_pps_sin_redondear_componentes(self):
        """
        Prueba con notas de componentes sin redondear (como en el Cuadro de Mérito real del portal):
        Suma ponderada sin redondear: 267.0 / 21 créditos = 12.7142857... -> 12.7143
        """
        cursos_unrounded = [
            {"crn": "5592", "nombre": "Infraestructura Como Codigo", "nota": 10.66, "creditos": 4},
            {"crn": "5598", "nombre": "Intel Art, Princip y Tecnic", "nota": 16.16, "creditos": 4},
            {"crn": "5636", "nombre": "Aplicac Moviles para Negocios", "nota": 11.06, "creditos": 4},
            {"crn": "6645", "nombre": "Deontologia Profesional", "nota": 15.40, "creditos": 2},
            {"crn": "3233", "nombre": "Metodolog Investigac Cientif", "nota": 14.90, "creditos": 3},
            {"crn": "5585", "nombre": "Agile Development", "nota": 9.995, "creditos": 4}
        ]

        pps = banner_sso_service.calcular_pps(cursos_unrounded)
        self.assertIsNotNone(pps)
        self.assertEqual(round(pps, 4), 12.7143)

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

    def test_cruce_fallido_y_exclusion_curso(self):
        """
        Verifica que ante un cruce fallido (créditos null):
        1. combinar_notas_creditos no lanza excepción y asigna creditos: None.
        2. calcular_pps excluye ese curso del numerador y denominador.
        Cursos válidos: 
        - Curso A: nota 16, créditos 4 -> 64
        - Curso B: nota 12, créditos 2 -> 24
        - Curso C (cruce fallido): nota 20, créditos None -> Excluido
        Resultado esperado: (64 + 24) / (4 + 2) = 88 / 6 = 14.6667
        """
        notas = [
            {"crn": "1001", "nombre": "Curso A", "nota": 16.0},
            {"crn": "1002", "nombre": "Curso B", "nota": 12.0},
            {"crn": "9999", "nombre": "Curso C Sin Creditos", "nota": 20.0}
        ]
        horario = [
            {"crn": "1001", "nombre": "Curso A", "creditos": 4},
            {"crn": "1002", "nombre": "Curso B", "creditos": 2}
        ]

        combinados = banner_sso_service.combinar_notas_creditos(notas, horario)
        self.assertIsNone(combinados[2]["creditos"])

        pps = banner_sso_service.calcular_pps(combinados)
        self.assertIsNotNone(pps)
        self.assertEqual(round(pps, 4), 14.6667)

if __name__ == "__main__":
    unittest.main()
