#include "rime_levers_api.h"
#include <dlfcn.h>
#include <iostream>
#include <string>
int main(int n,char**v){
 if(n!=6)return 2;
 void* lib=dlopen(v[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto get=(RimeApi*(*)())dlsym(lib,"rime_get_api");if(!get)return 4;auto api=get();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=v[2];t.user_data_dir=v[2];t.app_name="rime.kongime.learning";t.min_log_level=3;t.log_dir=v[2];
 api->setup(&t);api->initialize(&t);auto module=api->find_module("levers");if(!module||!module->get_api){api->finalize();return 5;}
 auto levers=(RimeLeversApi*)module->get_api();int count=-1;
 if(std::string(v[3])=="export")count=levers->export_user_dict("qingyan",v[4]);
 else if(std::string(v[3])=="import") {count=levers->import_user_dict("qingyan",v[4]);if(count>=0)count=levers->export_user_dict("qingyan",v[5]);}
 api->finalize();if(count<0)return 6;std::cout<<count<<std::endl;return 0;
}
