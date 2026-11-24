import sys
from pathlib import Path
from CLI.presenter import CLI
from CLI.commands import CatalogStrategy, GameStrategy, SystemStrategy, format_save
from Core.characters import CharacterManager, CharacterProfile, CharacterService
from Core.game import Game
from Core.saves import SaveManager, ProfileStorage, migrate_legacy
from Core.stats import Stats, Item, Modifier
from Infra.storage import (AppDataLocator, JsonFileStore, JsonProfileRepository, JsonGameRepository,
                           LegacyRepositoryFile)
from Infra.api import GenshinApiSource, StubCharacterSource, FallbackCharacterSource


def default_profiles():
    return [
        CharacterProfile("warrior_1", "Артур", "Воїн", Stats(130, 24, 0, 8, 0.10, 0.0, 100),
                         items=[Item("sword", "Сталевий меч", [Modifier("damage", 6)])]),
        CharacterProfile("mage_1", "Мерлін", "Маг", Stats(85, 10, 22, 2, 0.25, 0.10, 110),
                         items=[Item("staff", "Посох мудреця", [Modifier("magic", 5), Modifier("power", 0.1)])]),
        CharacterProfile("healer_1", "Ліра", "Цілитель", Stats(95, 9, 20, 4, 0.20, 0.0, 105)),
    ]


def parse_options(argv):
    data_dir = None
    rest = []
    for arg in argv:
        if arg.startswith("--data-dir="):
            data_dir = Path(arg.split("=", 1)[1]).expanduser()
        else:
            rest.append(arg)
    return data_dir, rest


def main():
    data_dir, argv = parse_options(sys.argv[1:])
    data_dir = data_dir or AppDataLocator.resolve()

    store = JsonFileStore(data_dir)
    manager = CharacterManager()
    storage = ProfileStorage(manager, JsonProfileRepository(store))
    saves = SaveManager(JsonGameRepository(store))
    service = CharacterService(manager, FallbackCharacterSource(GenshinApiSource(), StubCharacterSource()))

    try:
        storage.load(default_profiles())
        legacy = LegacyRepositoryFile(Path("repository.json"))
        legacy_data = legacy.read()
        if legacy_data:
            for message in migrate_legacy(legacy_data, storage, saves, legacy.modified_at()):
                print(message)
            legacy.mark_migrated()
    except OSError as e:
        print(f"[Попередження] Не вдалося прочитати дані: {e}")
    for warning in store.warnings:
        print(f"[Попередження] {warning}")

    cli = CLI()
    game_strategy = GameStrategy(Game(), manager, saves, cli)
    cli.use_strategy(CatalogStrategy(manager, service, storage, cli))
    cli.use_strategy(game_strategy)
    cli.use_strategy(SystemStrategy(cli, str(data_dir)))

    if argv:
        cli.exec_command(" ".join(argv))
        return

    cli.exec_command("help")
    latest = saves.latest()
    if latest:
        print(f"\nЗнайдено збереження {format_save(latest)}. Щоб продовжити, введіть: continue")
    while True:
        try:
            cmd = input("\n> ").strip()
            if cmd in ("exit", "quit"):
                game_strategy.autosave()
                break
            if cmd:
                cli.exec_command(cmd)
        except (KeyboardInterrupt, EOFError):
            game_strategy.autosave()
            break


if __name__ == "__main__":
    main()
