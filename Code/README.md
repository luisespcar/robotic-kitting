# ModularProgramming

Copia modular de `Code nueva homografia/Main.py` y `Code nueva homografia/StateMachine.py`.
Los originales no se modifican.

## Como ejecutar

```powershell
python "Code nueva homografia\ModularProgramming\Main.py"
```

`app_config.py` usa exclusivamente los recursos de `ModularProgramming`: `model/`, `config/` y `tests/`.

## Mapa rapido

- `Main.py`: entrada minima.
- `app.py`: bucle principal, UI y orquestacion.
- `app_config.py`: rutas y flags de camara/YOLO/RoboDK.
- `vision_detection.py`, `frame_processing.py`, `vision_worker.py`: deteccion y pipeline de vision.
- `camera_capture.py`: camara y reconexion.
- `robodk_live_updater.py`, `robot_worker.py`, `safety_control.py`: RoboDK, worker de robot y seguridad.
- `station_logic.py`: clase `StationLogic` ensamblada con mixins.
- `station_mixins/`: memoria, seguridad, RoboDK, tapas, celdas, bridge, cierre y evaluacion.
- `StateMachine.py`: wrapper de compatibilidad para `from StateMachine import StationLogic`.

El detector `bridge` se ejecuta siempre. La deteccion de mano queda disponible para la logica de tapas, pero no ordena paradas ni cambios automaticos de velocidad. Los controles `1/2/3/4` y `+/-` solicitan un cambio de velocidad al worker, que lo aplica cuando queda libre.
