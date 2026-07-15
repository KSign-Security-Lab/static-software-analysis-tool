#include <string.h>
#include <stddef.h>

#define PROFILE_BUFFER_SIZE 256

typedef struct {
    const unsigned char *schedule;
    size_t schedule_length;
} ChargingSchedule;

typedef struct {
    ChargingSchedule charging_schedule;
} SetChargingProfileReq;

static unsigned char g_profile_buffer[PROFILE_BUFFER_SIZE];

static void store_charging_profile(const unsigned char *schedule, size_t schedule_length) {
    memcpy(g_profile_buffer, schedule, schedule_length);
}

int handle_set_charging_profile(const SetChargingProfileReq *request) {
    const unsigned char *schedule = request->charging_schedule.schedule;
    size_t schedule_length = request->charging_schedule.schedule_length;
    store_charging_profile(schedule, schedule_length);
    return 0;
}
