#include <stddef.h>

int check_bound_fixed(int offset, int count) {
    if (offset < 0 || count < 0 || offset > 4096 - count) return -1;
    return offset + count;
}
