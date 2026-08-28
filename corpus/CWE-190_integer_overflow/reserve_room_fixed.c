#include <stdlib.h>

void *reserve_room_fixed(int len) {
    if (len < 0 || len == 2147483647) return NULL;
    return malloc((size_t)len + 1);
}
