import pendulum


# функции определения времени и периодов через pendulum
def get_now_at_saint_petersburg() -> pendulum.DateTime:
    return pendulum.now('Europe/Moscow')

def get_now_at_utc() -> pendulum.DateTime:
    return pendulum.now('UTC')

def get_now_at_spb_human_readable() -> str:
    return pendulum.now("Europe/Moscow").format("dddd, DD MMMM YYYY - HH:mm", locale="ru").capitalize()

# TODO: имплементировать функции для работы с периодами - https://pendulum.eustace.io/docs/#difference
