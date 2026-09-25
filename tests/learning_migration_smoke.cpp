#include "rime_levers_api.h"
#include <dlfcn.h>
#include <iostream>
int main(int n,char**v){
 if(n!=5)return 2;void*lib=dlopen(v[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=v[2];t.user_data_dir=v[2];t.app_name="rime.kongime.migrationtest";t.min_log_level=2;t.log_dir="/tmp";
 api->setup(&t);api->initialize(&t);auto module=api->find_module("levers");if(!module||!module->get_api)return 4;
 auto levers=(RimeLeversApi*)module->get_api();int imported=levers->import_user_dict("qingyan",v[3]);int exported=levers->export_user_dict("qingyan",v[4]);api->finalize();std::cout<<imported<<" "<<exported<<std::endl;return imported>0&&exported>0?0:5;
}
