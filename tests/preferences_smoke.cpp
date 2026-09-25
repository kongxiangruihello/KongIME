#include "qingyan-rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <string>
int main(int n,char**v){
 if(n<5)return 2;auto lib=dlopen(v[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=v[2];t.user_data_dir=v[2];t.app_name="rime.kongime.settings.test";t.min_log_level=2;t.log_dir="/tmp";
 api->setup(&t);api->initialize(&t);auto id=api->create_session();if(!api->select_schema(id,"qingyan"))return 4;
 api->set_option(id,"ascii_mode",false);api->simulate_key_sequence(id,v[3]);
 RIME_STRUCT(RimeContext,c);if(!api->get_context(id,&c))return 5;
 int found=-1;for(int i=0;i<c.menu.num_candidates;i++)if(std::string(c.menu.candidates[i].text)==v[4])found=i;
 api->free_context(&c);bool absent=n>5&&std::string(v[5])=="absent";
 if(absent && found<0){api->destroy_session(id);api->finalize();return 0;}
 if(found<0)return 7;api->select_candidate(id,found);
 RIME_STRUCT(RimeCommit,commit);if(!api->get_commit(id,&commit)){api->destroy_session(id);api->finalize();return absent?0:8;}
 const char* remaining=api->get_input(id);bool ok=std::string(commit.text)==v[4] && (!remaining || !*remaining);if(absent)ok=!ok;api->free_commit(&commit);api->destroy_session(id);api->finalize();
 std::cout<<(ok?"PASS candidate + commit":"FAIL")<<std::endl;return ok?0:9;
}
