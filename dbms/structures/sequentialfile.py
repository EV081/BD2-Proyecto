import struct
import math

from dbms.utils.pagemanager import PageManager 

class SequentialFile:
    
    RECORD_FORMAT = 'i30si20s20s20sf10s?' 
    RECORD_SIZE = struct.calcsize(RECORD_FORMAT)
    PAGE_SIZE = 4096 
    RECORDS_PER_PAGE = PAGE_SIZE // RECORD_SIZE

    def __init__(self, table_name, page_manager: PageManager):
        self.table_name = table_name
        self.pm = page_manager
        
        if not self.pm.exists(table_name):
            header = struct.pack('ii', 0, 0)
         
            header = header.ljust(self.PAGE_SIZE, b'\0')
            self.pm.write_page(table_name, 0, header)

    def _read_header(self):
        page0 = self.pm.read_page(self.table_name, 0) 
        return struct.unpack('ii', page0[:8])

    def binary_search(self, id_key: int):
        ordered_count, _ = self._read_header()
        low = 0
        high = ordered_count - 1
        
        while low <= high:
            mid = (low + high) // 2
           
            page_idx = (mid // self.RECORDS_PER_PAGE) + 1
            offset_in_page = (mid % self.RECORDS_PER_PAGE) * self.RECORD_SIZE
            
            page_data = self.pm.read_page(self.table_name, page_idx)
            record_data = page_data[offset_in_page : offset_in_page + self.RECORD_SIZE]
            rec, deleted = self._unpack_record(record_data)
            
            if rec.id == id_key:
                return rec if not deleted else None
            elif rec.id < id_key:
                low = mid + 1
            else:
                high = mid - 1
        return None