from utils.pagemanager import PageManager

if __name__ == "__main__":

    print("\n=== CREANDO PAGE MANAGER ===")
    pm = PageManager("users", "i5s?", page_size=44)

    print("\n=== INSERTS INICIALES ===")
    pm.add_record((1, b"Juan\x00", True))
    pm.add_record((2, b"Anaaa", False))
    pm.add_record((3, b"Pedro", True))
    pm.add_record((4, b"Maria", False))

    pm.print_page(0)

    print("\n=== DELETE (0,1) ===")
    pm.delete_record(0, 1)

    pm.print_page(0)

    print("\n=== INSERT (DEBE REUTILIZAR SLOT LIBRE) ===")
    pm.add_record((5, b"Luis\x00", True))

    pm.print_page(0)

    print("\n=== MÁS INSERTS (FORZAR NUEVA PÁGINA) ===")
    pm.add_record((6, b"Carlos", False))
    pm.add_record((7, b"Evaaa", True))
    pm.add_record((8, b"Rosaaa", False))
    pm.add_record((9, b"Diego", True))

    pm.print_page(0)
    pm.print_page(1)

    print("\n=== ESTADO FINAL ===")
    print("free_slots:", pm.free_slots)
    print("last_page:", pm.last_page)
    print("last_slot:", pm.last_slot)