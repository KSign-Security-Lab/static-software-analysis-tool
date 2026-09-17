#include <stdlib.h>

void *reserve_room_bad(int len) {
    return malloc(len + 1);
}
