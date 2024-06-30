import argparse
import asyncio
from concurrent import futures
from functools import partial
from RPi import GPIO
from gpiozero import Button
from spidev import SpiDev
from time import sleep
from random import randint as rd
from sys import stdout
from threading import Thread
from global_variables import field_height, field_width, refresh_rate, fps, max_items, player_graphic, enemy_graphic, item_graphic, easy, normal, hard, effects
from field import Field
from maps import ItemMap, BulMap
from entities import Creature, Item


#GPIO settings
char_to_segments = {
    '0': 0b00111111,
    '1': 0b00000110,
    '2': 0b01011011,
    '3': 0b01001111,
    '4': 0b01100110,
    '5': 0b01101101,
    '6': 0b01111100,
    '7': 0b00000111,
    '8': 0b01111111,
    '9': 0b01101111,
    '10': 0b01000000,
    'A': 0b00001001,
    'B': 0b00010010,
    'C': 0b00100100,
    'X': 0b01110110,
    'a': 0b00000001,
    'b': 0b00000010,
    'c': 0b00000100,
    'd': 0b00001000,
    'e': 0b00010000,
    'f': 0b00100000,
    'N': 0b00000000
}

MOSI = 6
SCLK = 5
CS = 13
GPIO.setmode(GPIO.BCM)
GPIO.setup(MOSI, GPIO.OUT)
GPIO.setup(SCLK, GPIO.OUT)
GPIO.setup(CS, GPIO.OUT)

def sspi(char):
    GPIO.output(CS, GPIO.LOW)
    for bit in range(8):
        GPIO.output(MOSI, char & 0x80)
        char <<= 1
        GPIO.output(SCLK, GPIO.HIGH)
        sleep(0.001)
        GPIO.output(SCLK, GPIO.LOW)
        sleep(0.001)
    GPIO.output(CS, GPIO.HIGH)

hspi = SpiDev()
hspi.open(0, 0)
hspi.max_speed_hz = 1350000
channel = 0

def read_adc(channel):
    if channel < 0 or channel > 7:
        return -1
    command = [1, (8 + channel) << 4, 0]
    response = hspi.xfer2(command)
    adc_out = ((response[1] & 3) << 8) + response[2]
    return adc_out

def scale_value(value):
    return value * field_width // 4095

def pressed(frame, bul_map):
    player.fire(frame, input=0, bul_map=bul_map)

button = Button(17)
button.when_pressed = lambda: pressed(frame, bul_map)

def reload_indicator(player):
    circle = ['a', 'b', 'c', 'd', 'e', 'f']
    recode = []
    for segment in char_to_segments[circle]:
        recode.append(segment)
        sspi(recode)
        sleep((player.reload // fps) / len(circle))
    sspi('N')

def detect_reload(player, clear, reload_indicator):
    global reloading
    reloading = True
    while not clear:
        if player.reloading:
            reload_thread = Thread(target=reload_indicator, args=player)
            reload_thread.start()
            reload_thread.join()
    sleep(0.2)
    reloading = False

#choose game level from command line
parser = argparse.ArgumentParser(description="")
parser.add_argument("--level", type=str, help="choose game level from easy, normal, and hard")
args = parser.parse_args()
level = args.level.lower()
while True:
    if level == "easy":
        mode = easy
        break
    elif level == "normal":
        mode = normal
        break
    elif level == "hard":
        mode = hard
        break
    else:
        level = input("choose game level from easy, normal, and hard: ").lower()

ehp, evel, ebul_vel, erapid_fire, ereload, estart, php, pvel, pbul_vel, prapid_fire, preload = mode.values()


#initialize new game
player = Creature(hp=php,
                  width=len(player_graphic[0]),
                  pos=rd((len(player_graphic[0]) // 2), field_width - (len(player_graphic[0]) // 2) - 1),
                  vel=pvel,
                  bul_dam=1,
                  bul_vel=pbul_vel,
                  burst=True,
                  rapid_fire=prapid_fire,
                  reload=preload)
enemy = Creature(hp=ehp,
                 width=len(enemy_graphic[0]),
                 pos=rd((len(enemy_graphic[0]) // 2), field_width - (len(enemy_graphic[0]) // 2) - 1),
                 vel=evel,
                 bul_dam=1,
                 bul_vel=ebul_vel,
                 burst=False,
                 rapid_fire=erapid_fire,
                 reload=ereload)
frame = 0
clear = 0
reloading = False
bul_map = BulMap()
item_map = ItemMap()
field = Field(player=player, enemy=enemy, item_map=item_map, bul_map=bul_map)
item_list = []
for col in field.field:
    print(col)
    sleep(0.2)
frame += 1
try:
    reload_thread = Thread(target=detect_reload, args=(player, clear, reload_indicator))
    reload_thread.start()
    pre_php = 10000

    #main game start
    while not clear:
        sleep(refresh_rate)
        #item appearance probability will increase according to frame by exponentially
        if (len(item_list) < max_items) and not rd(0, 5 * fps):
            item_list.append(Item(width=len(item_graphic),
                                  pos=(rd(2, field_width - 3), rd(len(enemy_graphic), field_height - len(player_graphic) - 1)),
                                  effect=list(effects.keys())[rd(0, len(effects) - 1)],
                                  player=player,
                                  enemy=enemy,
                                  item_map=item_map,
                                  bul_map=bul_map,
                                  item_list=item_list))
        bul_map.advance_frame(frame)
        adc = read_adc(channel)
        player.change_pos(scale_value(adc), frame)
        enemy.change_pos(rd((len(enemy_graphic[0]) // 2), field_width - (len(enemy_graphic[0]) // 2) - 1), frame)
        if frame > estart * fps:
            enemy.fire(frame, input=rd(0,15), bul_map=bul_map)
        player.fire(frame, input=1, bul_map=bul_map)
        field = Field(player=player, enemy=enemy, bul_map=bul_map)
        field.print_field()
        stdout.flush()
        if (not reloading) and (pre_php != player.hp):
            sspi(player.hp)
            pre_php = player.hp
        frame += 1
        if enemy.hp == 0:
            clear = 1
            break
        elif player.hp == 0:
            clear = -1
            break
    
    #game ending process
    reload_thread.join()
    for item in item_list:
        item.sustain = 0
        item.hp = 0
    if clear > 0:
        for col, s_col in enumerate(field.field):
            for row, s_row in enumerate(s_col):
                if s_row == " ":
                    field.field[col] = s_col[:row] + "□" + s_col[row + 1:]
                    s_col = field.field[col]
        field.print_field()
        sleep(0.5)

        async def command_line(field):
            message = "!YOU WIN!"
            message_begin = len(field.field[0]) // 2 - len(message) // 2
            for col, f_col in enumerate(reversed(field.field)):
                for row, f_row in enumerate(f_col):
                    if col == len(field.field) // 2 and row > message_begin and row <= message_begin + len(message):
                        field.field[len(field.field) - col - 1] = f_col[:row] + message[row - message_begin - 1] + f_col[row + 1:]
                    else:
                        field.field[len(field.field) - col - 1] = f_col[:row] + " " + f_col[row + 1:]
                    f_col = field.field[len(field.field) - col - 1]
                    field.print_field()
                    await asyncio.sleep(1/150)

        async def led():
            count = 0
            circle = ('A', 'B', 'C')
            while True:
                sspi(circle[count % len(circle)])
                count += 1
                await asyncio.sleep(1 / 30)
        
        async def main(field):
            loop = asyncio.get_running_loop()
            with futures.ProcessPoolExecutor() as pool:
                command_line_future = loop.run_in_executor(pool, partial(command_line, field))
                led_future = loop.run_in_executor(pool, led)
                await command_line_future
                await led_future
        
        asyncio.run(main(field))

    elif clear < 0:
        for col, s_col in enumerate(field.field):
            for row, s_row in enumerate(s_col):
                if s_row == " ":
                    field.field[col] = s_col[:row] + "■" + s_col[row + 1:]
                    s_col = field.field[col]
                elif s_row == "■":
                    field.field[col] = s_col[:row] + "□" + s_col[row + 1:]
                    s_col = field.field[col]
        field.print_field()
        sleep(0.5)

        async def command_line(field):
            message = "YOU LOSE..."
            message_begin = len(field.field[0]) // 2 - len(message) // 2
            for count, col in enumerate(reversed(field.field)):
                del_list = [True for row in col]
                while any(del_list):
                    del_field = rd(0, len(col) - 1)
                    while field.field[len(field.field) - count - 1] and not del_list[del_field]:
                        del_field = rd(0, len(col) - 1)
                    if count == len(field.field) // 2 and del_field > message_begin and del_field <= message_begin + len(message):
                        field.field[len(field.field) - count - 1] = col[:del_field] + message[del_field - message_begin - 1] + col[del_field + 1:]
                    else:
                        field.field[len(field.field) - count - 1] = col[:del_field] + " " + col[del_field + 1:]
                    del_list[del_field] = False
                    col = field.field[len(field.field) - count - 1]
                    field.print_field()
                    await asyncio.sleep(1/150)

        async def led():
            count = 0
            X = ('X', 'N')
            while True:
                sspi(X[count % len(X)])
                count += 1
                await asyncio.sleep(0.5)

        async def main(field):
            loop = asyncio.get_running_loop()
            with futures.ProcessPoolExecutor() as pool:
                command_line_future = loop.run_in_executor(pool, partial(command_line, field))
                led_future = loop.run_in_executor(pool, led)
                await command_line_future
                await led_future
        
        asyncio.run(main(field))

except KeyboardInterrupt:
    print("The game was interrupted.")
    pass

finally:
    GPIO.cleanup()