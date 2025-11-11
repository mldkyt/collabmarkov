from sqlalchemy import create_engine, MetaData, Table, Column, VARCHAR, insert, select, BOOLEAN, update, Connection

engine = create_engine(
    "sqlite:///data/collabmarkov.db",
    connect_args={"timeout": 30},
    echo=True
)

md_obj = MetaData()

posts_table = Table(
    "posts",
    md_obj,
    Column("id", VARCHAR, primary_key=True),
    Column("text", VARCHAR),
    Column("has_cw", BOOLEAN),
    Column("visibility", VARCHAR),
    Column("author", VARCHAR)
)

settings_table = Table(
    "settings",
    md_obj,
    Column("author", VARCHAR, primary_key=True),
    Column("setting", VARCHAR, primary_key=True),
    Column("value", VARCHAR, nullable=False)
)

responded_dms_table = Table(
    "responded_dms",
    md_obj,
    Column("id", VARCHAR, primary_key=True)
)

follows_table = Table(
    "follows",
    md_obj,
    Column("id", VARCHAR, primary_key=True)
)

md_obj.create_all(engine, checkfirst=True)

def get_setting(c: Connection, acct: str, setting: str, default: str) -> str:
    a = c.execute(
        select(settings_table.c.value)
        .where((settings_table.c.author == acct) & (settings_table.c.setting == setting))
    ).fetchone()

    if a is not None:
        return a[0]

    return default

def set_setting(c: Connection, acct: str, setting: str, value: str):
    a = c.execute(
        select(settings_table.c.value)
        .where((settings_table.c.author == acct) & (settings_table.c.setting == setting))
    ).fetchone()

    if a is not None:
        c.execute(
            update(settings_table)
            .values(value=value)
            .where((settings_table.c.author == acct) & (settings_table.c.setting == setting))
        )
    else:
        c.execute(
            insert(settings_table)
            .values(author=acct, setting=setting, value=value)
        )

