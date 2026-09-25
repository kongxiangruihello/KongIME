#include "rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <string>
int main(int argc,char**argv){
 if(argc!=3)return 2;auto lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.app_name="rime.kongime013.test";t.min_log_level=2;t.log_dir="/tmp";
 api->setup(&t);api->initialize(&t);api->start_maintenance(true);api->join_maintenance_thread();auto id=api->create_session();if(!api->select_schema(id,"qingyan"))return 4;api->set_option(id,"ascii_mode",false);
 for(auto input:{"qy","qing'y","qingyan"}){
  api->clear_composition(id);api->simulate_key_sequence(id,input);RIME_STRUCT(RimeContext,c);if(!api->get_context(id,&c))return 5;
  std::cout<<input<<" count="<<c.menu.num_candidates<<std::endl;for(int i=0;i<c.menu.num_candidates;i++)std::cout<<i<<":"<<c.menu.candidates[i].text<<" / "<<(c.menu.candidates[i].comment?c.menu.candidates[i].comment:"")<<std::endl;
  if(c.menu.num_candidates<5||std::string(c.menu.candidates[0].text)!="轻言")return 6;
  if(!c.menu.candidates[0].comment||std::string(c.menu.candidates[0].comment).find("qing")==std::string::npos)return 7;
  int offset=c.menu.page_no*c.menu.page_size+c.menu.num_candidates;api->free_context(&c);
  RimeCandidateListIterator it{};if(!api->candidate_list_from_index(id,&it,offset)||!api->candidate_list_next(&it))return 8;
  std::string expected=it.candidate.text;if(it.index!=offset)return 9;api->candidate_list_end(&it);
  if(!api->select_candidate(id,offset))return 10;RIME_STRUCT(RimeCommit,commit);if(!api->get_commit(id,&commit)||std::string(commit.text)!=expected)return 11;api->free_commit(&commit);
 }
 api->destroy_session(id);api->finalize();std::cout<<"PASS abbreviation, mixed spelling, pinyin comments, expanded candidate index and commit"<<std::endl;
}
