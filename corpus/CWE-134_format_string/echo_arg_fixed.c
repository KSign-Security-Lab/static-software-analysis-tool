#include <stdio.h>

int echo_arg_fixed(int argc, char **argv) {
    if (argc > 1) fputs(argv[1], stdout);
    return 0;
}
