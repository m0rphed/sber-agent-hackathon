import marimo

__generated_with = "0.18.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import rich
    return mo, rich


@app.cell
def _():
    from collections.abc import Callable

    from langgraph_app.api.yazzh_final import ApiClientUnified, __api__


    async_yazzh_client = ApiClientUnified(verbose=False)


    async def do_request(func: Callable, **kwargs) -> dict:
        async with async_yazzh_client as _client:
            result = await func(**kwargs)
            json_res = result['json']
            return json_res['data']
    return async_yazzh_client, do_request


@app.cell
def _(mo):
    run_btn_ui = mo.ui.run_button(label='Запуск запросов к API')
    return (run_btn_ui,)


@app.cell
def _(run_btn_ui):
    run_btn_ui
    return


@app.cell
def _(async_yazzh_client, do_request):
    async def get_all_districts() -> list[dict]:
        districts = await do_request(async_yazzh_client.get_districts)
        return districts


    async def get_all_districts_names() -> list[str]:
        all_districts = await get_all_districts()
        return [district['name'] for district in all_districts]


    async def get_all_districts_name_map() -> dict[str, dict]:
        all_districts = await get_all_districts()
        all_districts_sorted = sorted(all_districts, key=lambda x: x['id'])
        return {dst['name']: dst for dst in all_districts_sorted}

    return get_all_districts, get_all_districts_names


@app.cell
async def _(get_all_districts_names, mo, rich, run_btn_ui):
    mo.stop(not run_btn_ui.value, mo.md('запрос: получение имён всех районов'))

    # получение всех ИМЕН РАЙОНОВ
    district_names = await get_all_districts_names()
    rich.print(district_names)
    return


@app.cell
async def _(get_all_districts, mo, rich, run_btn_ui):
    mo.stop(not run_btn_ui.value, mo.md('запрос: получение информации о каждом районов'))
    _xs = await get_all_districts()
    _xs = sorted(_xs, key=lambda x: x['id'])
    rich.print(_xs)
    return


@app.cell
def _():
    all_districts_names = [
        'Неизвестно',
        'Василеостровский',
        'Петроградский',
        'Калининский',
        'Красногвардейский',
        'Невский',
        'Фрунзенский',
        'Московский',
        'Кировский',
        'Красносельский',
        'Петродворцовый',
        'Центральный',
        'Адмиралтейский',
        'Приморский',
        'Пушкинский',
        'Выборгский',
        'Колпинский',
        'Курортный',
        'Кронштадтский',
        'Гатчинский ЛО',
        'Всеволожский ЛО',
        'Лужский ЛО',
        'Приозерский ЛО',
        'Кингисеппский ЛО',
        'Тосненский ЛО',
        'Кировский ЛО',
        'Сосновоборский ЛО',
        'Волховский ЛО',
        'Выборгский ЛО',
        'Ломоносовский ЛО',
        'Бокситогорский ЛО',
        'Киришский ЛО',
        'Лодейнопольский ЛО',
        'Подпорожский ЛО',
        'Сланцевский ЛО',
        'Тихвинский ЛО',
        'Волосовский ЛО',
    ]
    return (all_districts_names,)


@app.cell
def _(all_districts_names):
    oblast_district = [x for x in all_districts_names if x.endswith('ЛО')]
    city_district = [x for x in all_districts_names if not x.endswith('ЛО')]
    city_district
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
