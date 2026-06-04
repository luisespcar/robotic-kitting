from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Tuple

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - allow script to still show helpful error
    print("Pillow is required. Install with: pip install pillow")
    raise

import tkinter as tk


CONFIG_PATH = Path(__file__).with_name("config").joinpath("homography.json")


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def click_points(image_path: Path, expected_n: int | None = None) -> List[Tuple[float, float]]:
    if not image_path.exists():
        raise FileNotFoundError(f"No se pudo abrir la imagen: {image_path}")

    pil_img = Image.open(str(image_path)).convert("RGBA")
    w, h = pil_img.size

    points: List[Tuple[float, float]] = []

    class ClickApp:
        def __init__(self, pil_image: Image.Image):
            self.root = tk.Tk()
            self.root.title("Clicar puntos - pulsa 'q' o 'Finish' para terminar")
            self.photo = ImageTk.PhotoImage(pil_image)
            self.canvas = tk.Canvas(self.root, width=w, height=h)
            self.canvas.pack()
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
            self.canvas.bind("<Button-1>", self.on_click)
            self.root.bind("q", lambda e: self.finish())
            btn = tk.Button(self.root, text="Finish", command=self.finish)
            btn.pack(fill="x")

        def on_click(self, event):
            x, y = event.x, event.y
            points.append((float(x), float(y)))
            r = 6
            idx = len(points)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill="green", outline="")
            self.canvas.create_text(x + 12, y - 8, text=str(idx), fill="green", font=("Helvetica", 12, "bold"))
            if expected_n and len(points) >= expected_n:
                print(f"Se han seleccionado {len(points)} puntos (esperados: {expected_n}). Pulsa 'Finish' o 'q' para confirmar.")

        def finish(self):
            self.root.quit()
            self.root.destroy()

        def run(self):
            self.root.mainloop()

    app = ClickApp(pil_img)
    app.run()
    return points


def prompt_robot_points(n: int, current: List[List[float]] | None = None) -> List[List[float]]:
    out: List[List[float]] = []
    current = current or []
    for i in range(n):
        cur = current[i] if i < len(current) else [0.0, 0.0]
        raw = input(f"Punto {i+1} robot mm (formato 'x,y') [actual: {cur[0]},{cur[1]}] -> ").strip()
        if raw == "":
            out.append([float(cur[0]), float(cur[1])])
            continue
        try:
            x_str, y_str = raw.split(",")
            out.append([float(x_str), float(y_str)])
        except Exception:
            print("Formato inválido, se usará el valor actual.")
            out.append([float(cur[0]), float(cur[1])])
    return out


def prompt_manual_image_points(n: int, current: List[List[float]] | None = None) -> List[List[float]]:
    out: List[List[float]] = []
    current = current or []
    for i in range(n):
        cur = current[i] if i < len(current) else [0.0, 0.0]
        raw = input(f"Punto {i+1} imagen px (formato 'u,v') [actual: {cur[0]},{cur[1]}] -> ").strip()
        if raw == "":
            out.append([float(cur[0]), float(cur[1])])
            continue
        try:
            u_str, v_str = raw.split(",")
            out.append([float(u_str), float(v_str)])
        except Exception:
            print("Formato inválido, se usará el valor actual.")
            out.append([float(cur[0]), float(cur[1])])
    return out


def edit_interactive(cfg_path: Path):
    cfg = load_config(cfg_path)
    img_path = Path(cfg.get("source_image", ""))
    image_points = cfg.get("image_points", [])
    robot_points = cfg.get("robot_points_mm", [])

    # Detectar automáticamente imagen 'Homografía' en el Escritorio del usuario
    def find_desktop_homografia() -> Path | None:
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            return None
        candidates = []
        for ext in (".jpg", ".jpeg", ".png", ".bmp"): 
            for name in ("Homografía", "Homografia", "Homograf\u00eda"):
                p = desktop / (name + ext)
                if p.exists():
                    candidates.append(p)
        # Busqueda más amplia: cualquier fichero del escritorio que contenga 'homograf' (insensible a mayúsculas)
        if not candidates:
            for p in desktop.iterdir():
                if p.is_file() and "homograf" in p.name.lower():
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                        candidates.append(p)
        return candidates[0] if candidates else None

    desktop_img = find_desktop_homografia()
    if desktop_img:
        print(f"Imagen de Escritorio encontrada: {desktop_img}")
        img_path = desktop_img
        # Actualizar temporalmente la ruta en la configuración para que quede guardada al finalizar
        cfg["source_image"] = str(img_path)

    print("Modo interactivo:\n1) Clicar en la imagen para obtener puntos\n2) Escribir coordenadas manualmente\n3) Editar actuales\n")
    print(f"Usando imagen: {img_path}")
    mode = input("Selecciona modo (click/manual/edit) [click]: ").strip().lower() or "click"

    if mode == "click":
        expected = len(image_points) if image_points else 9
        pts, pts_robot = click_points(img_path, expected_n=expected, ask_robot=True, start_index=1)
        if expected and len(pts) != expected:
            print(f"Advertencia: se esperaban {expected} puntos pero se obtuvieron {len(pts)}.")
        image_points = [[float(x), float(y)] for x, y in pts]
        # Merge robot points: prefer dialog-provided values, fall back to existing array
        if pts_robot:
            robot_points = pts_robot
        else:
            robot_points = prompt_robot_points(len(image_points), current=robot_points)

    elif mode == "manual":
        n = int(input(f"Número de puntos a editar/crear [{len(image_points)}]: ").strip() or len(image_points))
        image_points = prompt_manual_image_points(n, current=image_points)
        robot_points = prompt_robot_points(n, current=robot_points)

    elif mode == "edit":
        print("Puntos actuales de imagen:")
        for i, p in enumerate(image_points):
            print(f"{i+1}: {p}")
        edit_idx = input("Índice a editar (o ENTER para saltar): ").strip()
        if edit_idx:
            idx = int(edit_idx) - 1
            raw = input("Nuevo punto imagen 'u,v' -> ").strip()
            u, v = raw.split(",")
            image_points[idx] = [float(u), float(v)]

        print("Puntos actuales robot:")
        for i, p in enumerate(robot_points):
            print(f"{i+1}: {p}")
        edit_idx = input("Índice robot a editar (o ENTER para salir): ").strip()
        if edit_idx:
            idx = int(edit_idx) - 1
            raw = input("Nuevo punto robot 'x,y' -> ").strip()
            x, y = raw.split(",")
            robot_points[idx] = [float(x), float(y)]

    else:
        print("Modo desconocido. Saliendo.")
        return

    cfg["image_points"] = image_points
    cfg["robot_points_mm"] = robot_points
    cfg["edited_with"] = str(Path(__file__).resolve())
    save_config(cfg_path, cfg)
    print(f"Guardado {cfg_path} con {len(image_points)} puntos.")


def main(argv: List[str] | None = None):
    argv = argv or sys.argv[1:]
    cfg_path = Path(argv[0]) if argv else CONFIG_PATH
    if not cfg_path.exists():
        print(f"No se encontró el archivo de configuración: {cfg_path}")
        return
    edit_interactive(cfg_path)


if __name__ == "__main__":
    main()
